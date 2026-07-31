#!/usr/bin/env python
"""Recorre la plataforma de principio a fin y deja el proyecto generado en disco.

Sirve para comprobar la instalación sin levantar Docker ni gastar llamadas al modelo:
usa SQLite, la cola en memoria y el proveedor de IA determinista.

    python scripts/demo.py --salida ./generado --peticion "Necesito un sistema para un gimnasio"
"""

from __future__ import annotations

import argparse
import asyncio
import io
import shutil
import zipfile
from pathlib import Path

from factory.config import Settings
from factory.container import build_container
from factory.domain.entities import Organization, User
from factory.domain.value_objects import Email
from factory.infrastructure.security.hasher import Pbkdf2PasswordHasher


async def run(prompt: str, name: str, output: Path) -> int:
    settings = Settings(
        env="development",
        database_url="sqlite+aiosqlite:///./demo.db",
        redis_url="",
        llm_provider="fake",
        log_level="ERROR",
    )
    container = await build_container(settings)
    await container.database.create_all()

    organization = Organization.create("Organización de demostración")
    user = User(
        organization_id=organization.id,
        email=Email("demo@example.com"),
        password_hash=Pbkdf2PasswordHasher().hash("contrasena-de-demostracion"),
    )
    async with container.unit_of_work() as uow:
        await uow.organizations.add(organization)
        await uow.users.add(user)

    print(f"1. Creando el proyecto «{name}»")
    project, _ = await container.projects.create(user=user, name=name, prompt=prompt)

    print("2. Conversando con la IA")
    await container.conversations.send_message(user=user, project_id=project.id, content=prompt)
    conversation = await container.conversations.get(user=user, project_id=project.id)
    for question in conversation.pending_questions:
        print(f"   · {question.text}")
        await container.conversations.answer(
            user=user,
            project_id=project.id,
            question_id=question.id,
            answer=question.options[0] if question.options else "Sí",
        )

    requirements = await container.projects.requirements(user=user, project_id=project.id)
    if requirements:
        print(f"   dominio detectado: {requirements.business_domain}")

    print("3. Construyendo (pipeline completo de agentes)")
    build = await container.builds.request_build(user=user, project_id=project.id)
    report = await container.builds.execute_build(project_id=project.id, build_id=build.id)
    if not report.succeeded:
        print(f"   la construcción ha fallado: {report.error}")
        await container.close()
        return 1
    for stage in report.build.stages:
        print(f"   {stage.status:>9}  {stage.name}")

    print("4. Desplegando")
    deployment = await container.deployments.request_deployment(user=user, project_id=project.id)
    result = await container.deployments.execute_deployment(
        project_id=project.id, deployment_id=deployment.id
    )

    async with container.unit_of_work() as uow:
        stored = await uow.builds.get(build.id)
    assert stored is not None and stored.bundle_key is not None

    bundle = await container.storage.get(stored.bundle_key)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        archive.extractall(output)
        file_count = len(archive.namelist())

    print()
    print(f"Proyecto generado: {file_count} ficheros en {output.resolve()}")
    print(f"URL entregada:     {result.url}")
    print()
    print("Para arrancarlo:")
    print(f"   cd {output}/{project.slug} && ./install.sh")

    await container.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--peticion",
        default="Necesito un sistema para un gimnasio con reservas de clases y cuotas",
        help="Descripción en lenguaje natural del software que se necesita",
    )
    parser.add_argument("--nombre", default="Gimnasio Titán", help="Nombre del proyecto")
    parser.add_argument(
        "--salida", type=Path, default=Path("./generado"), help="Directorio de destino"
    )
    args = parser.parse_args()
    return asyncio.run(run(args.peticion, args.nombre, args.salida))


if __name__ == "__main__":
    raise SystemExit(main())
