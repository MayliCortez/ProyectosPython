"""Recorrido completo de la plataforma a través de la API HTTP."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from factory.application.services.build_service import BUILD_JOB
from factory.application.services.deployment_service import DEPLOY_JOB
from factory.container import Container
from factory.infrastructure.events import InMemoryEventBus
from factory.infrastructure.queue import InMemoryJobQueue
from factory.infrastructure.storage import InMemoryObjectStorage

API = "/api/v1"


class TestAutenticacion:
    async def test_registro_emite_token_y_crea_organizacion(self, client: AsyncClient) -> None:
        response = await client.post(
            f"{API}/auth/register",
            json={
                "email": "fundadora@acme.test",
                "password": "contrasena-larga",
                "organization_name": "Acme S.L.",
                "full_name": "Ada",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["role"] == "owner"
        assert body["access_token"]

    async def test_no_se_permiten_correos_duplicados(self, client: AsyncClient) -> None:
        payload = {
            "email": "repetida@acme.test",
            "password": "contrasena-larga",
            "organization_name": "Acme",
        }
        assert (await client.post(f"{API}/auth/register", json=payload)).status_code == 201
        segunda = await client.post(f"{API}/auth/register", json=payload)
        assert segunda.status_code == 409
        assert segunda.json()["code"] == "conflict"

    async def test_contrasena_incorrecta_no_revela_si_la_cuenta_existe(
        self, client: AsyncClient
    ) -> None:
        await client.post(
            f"{API}/auth/register",
            json={
                "email": "persona@acme.test",
                "password": "contrasena-larga",
                "organization_name": "Acme",
            },
        )
        mala = await client.post(
            f"{API}/auth/login", json={"email": "persona@acme.test", "password": "otra-cosa"}
        )
        inexistente = await client.post(
            f"{API}/auth/login", json={"email": "nadie@acme.test", "password": "otra-cosa"}
        )
        assert mala.status_code == inexistente.status_code == 403
        assert mala.json()["message"] == inexistente.json()["message"]

    async def test_sin_token_no_hay_acceso(self, client: AsyncClient) -> None:
        assert (await client.get(f"{API}/projects")).status_code == 403

    async def test_token_invalido_se_rechaza(self, client: AsyncClient) -> None:
        response = await client.get(
            f"{API}/projects", headers={"Authorization": "Bearer no-es-un-token"}
        )
        assert response.status_code == 403


class TestSistema:
    async def test_sonda_de_vida(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    async def test_sonda_de_disponibilidad(self, client: AsyncClient) -> None:
        body = (await client.get("/ready")).json()
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["llm"] == "fake"


class TestProyectos:
    async def test_crear_y_listar(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        creado = await client.post(
            f"{API}/projects",
            json={"name": "Gimnasio Titán", "prompt": "Necesito un sistema para un gimnasio"},
            headers=auth_headers,
        )
        assert creado.status_code == 201
        cuerpo = creado.json()
        assert cuerpo["project"]["slug"] == "gimnasio-titan"
        assert cuerpo["conversation_id"]

        listado = await client.get(f"{API}/projects", headers=auth_headers)
        assert [p["id"] for p in listado.json()] == [cuerpo["project"]["id"]]

    async def test_proyecto_inexistente_devuelve_404(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get(f"{API}/projects/no-existe", headers=auth_headers)
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    async def test_no_se_ven_proyectos_de_otra_organizacion(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        propio = (
            await client.post(f"{API}/projects", json={"name": "Privado"}, headers=auth_headers)
        ).json()["project"]["id"]

        otra = await client.post(
            f"{API}/auth/register",
            json={
                "email": "rival@otra.test",
                "password": "contrasena-larga",
                "organization_name": "Otra",
            },
        )
        cabeceras_rival = {"Authorization": f"Bearer {otra.json()['access_token']}"}

        response = await client.get(f"{API}/projects/{propio}", headers=cabeceras_rival)
        assert response.status_code == 403

    async def test_archivar_bloquea_los_cambios(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        project_id = (
            await client.post(f"{API}/projects", json={"name": "Efímero"}, headers=auth_headers)
        ).json()["project"]["id"]

        archivado = await client.post(f"{API}/projects/{project_id}/archive", headers=auth_headers)
        assert archivado.json()["status"] == "archived"

        renombrado = await client.patch(
            f"{API}/projects/{project_id}", json={"name": "Otro"}, headers=auth_headers
        )
        assert renombrado.status_code == 409


class TestConversacion:
    async def test_el_chat_captura_requisitos_y_propone_modulos(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        project_id = (
            await client.post(f"{API}/projects", json={"name": "Gimnasio"}, headers=auth_headers)
        ).json()["project"]["id"]

        respuesta = await client.post(
            f"{API}/projects/{project_id}/conversation/messages",
            json={"content": "Necesito un sistema para un gimnasio con reserva de clases"},
            headers=auth_headers,
        )
        assert respuesta.status_code == 200
        conversacion = respuesta.json()
        assert conversacion["messages"][-1]["role"] == "assistant"

        requisitos = await client.get(
            f"{API}/projects/{project_id}/requirements", headers=auth_headers
        )
        assert requisitos.status_code == 200
        assert requisitos.json()["business_domain"] == "gym"
        assert "reservas" in requisitos.json()["suggested_modules"]

        proyecto = await client.get(f"{API}/projects/{project_id}", headers=auth_headers)
        assert proyecto.json()["status"] == "specified"

    async def test_las_preguntas_pendientes_bloquean_la_construccion(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        container: Container,
    ) -> None:
        container.llm.answer_questions = False  # type: ignore[union-attr]
        project_id = (
            await client.post(f"{API}/projects", json={"name": "Gimnasio"}, headers=auth_headers)
        ).json()["project"]["id"]

        conversacion = (
            await client.post(
                f"{API}/projects/{project_id}/conversation/messages",
                json={"content": "Necesito un sistema para un gimnasio"},
                headers=auth_headers,
            )
        ).json()
        assert conversacion["pending_questions"]

        bloqueada = await client.post(f"{API}/projects/{project_id}/builds", headers=auth_headers)
        assert bloqueada.status_code == 409

        pregunta = conversacion["pending_questions"][0]["id"]
        respondida = await client.post(
            f"{API}/projects/{project_id}/conversation/answers",
            json={"question_id": pregunta, "answer": "Mensual y anual"},
            headers=auth_headers,
        )
        assert respondida.status_code == 200
        assert pregunta in respondida.json()["answers"]

    async def test_responder_una_pregunta_inexistente_falla(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        project_id = (
            await client.post(f"{API}/projects", json={"name": "Proyecto"}, headers=auth_headers)
        ).json()["project"]["id"]

        response = await client.post(
            f"{API}/projects/{project_id}/conversation/answers",
            json={"question_id": "fantasma", "answer": "hola"},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestModulos:
    async def test_el_catalogo_se_publica_entero(self, client: AsyncClient) -> None:
        catalogo = (await client.get(f"{API}/modules")).json()
        assert len(catalogo) == 19
        assert {"key", "depends_on", "tables"} <= set(catalogo[0])

    async def test_busqueda_en_el_catalogo(self, client: AsyncClient) -> None:
        resultados = (await client.get(f"{API}/modules", params={"q": "factura"})).json()
        assert [m["key"] for m in resultados] == ["billing"]

    async def test_instalar_arrastra_dependencias(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        project_id = (
            await client.post(f"{API}/projects", json={"name": "Con módulos"}, headers=auth_headers)
        ).json()["project"]["id"]

        response = await client.post(
            f"{API}/projects/{project_id}/modules",
            json={"modules": ["reservas"]},
            headers=auth_headers,
        )
        assert response.status_code == 200
        instalados = {m["module_key"] for m in response.json()["installed"]}
        assert {"reservas", "agenda", "users"} <= instalados
        assert response.json()["warnings"]

    async def test_eliminar_un_modulo_con_dependientes_se_rechaza(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        project_id = (
            await client.post(f"{API}/projects", json={"name": "Con módulos"}, headers=auth_headers)
        ).json()["project"]["id"]
        await client.post(
            f"{API}/projects/{project_id}/modules",
            json={"modules": ["reservas"]},
            headers=auth_headers,
        )

        response = await client.post(
            f"{API}/projects/{project_id}/modules/remove",
            json={"modules": ["agenda"]},
            headers=auth_headers,
        )
        assert response.status_code == 409
        assert response.json()["code"] == "module_dependency_error"

    async def test_eliminar_en_cascada_deja_el_resto_intacto(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        project_id = (
            await client.post(f"{API}/projects", json={"name": "Con módulos"}, headers=auth_headers)
        ).json()["project"]["id"]
        await client.post(
            f"{API}/projects/{project_id}/modules",
            json={"modules": ["reservas", "crm"]},
            headers=auth_headers,
        )

        response = await client.post(
            f"{API}/projects/{project_id}/modules/remove",
            json={"modules": ["agenda"], "cascade": True},
            headers=auth_headers,
        )
        assert response.status_code == 200
        restantes = {m["module_key"] for m in response.json()["installed"]}
        assert "reservas" not in restantes
        assert {"users", "crm"} <= restantes


class TestConstruccionYDespliegue:
    async def _proyecto_listo(self, client: AsyncClient, auth_headers: dict[str, str]) -> str:
        project_id = (
            await client.post(
                f"{API}/projects",
                json={"name": "Gimnasio Titán", "prompt": "Sistema para un gimnasio"},
                headers=auth_headers,
            )
        ).json()["project"]["id"]
        await client.post(
            f"{API}/projects/{project_id}/conversation/messages",
            json={"content": "Necesito un sistema para un gimnasio con reservas y cuotas"},
            headers=auth_headers,
        )
        return project_id

    async def test_flujo_completo_hasta_la_url_funcional(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        container: Container,
        queue: InMemoryJobQueue,
        storage: InMemoryObjectStorage,
        events: InMemoryEventBus,
    ) -> None:
        project_id = await self._proyecto_listo(client, auth_headers)

        # 1. La API solo encola: responde 202 sin haber construido nada todavía.
        encolado = await client.post(f"{API}/projects/{project_id}/builds", headers=auth_headers)
        assert encolado.status_code == 202
        build_id = encolado.json()["id"]
        assert encolado.json()["status"] == "queued"

        trabajo = await queue.reserve(timeout_seconds=1)
        assert trabajo is not None and trabajo.kind == BUILD_JOB

        # 2. El worker ejecuta el pipeline completo.
        report = await container.builds.execute_build(project_id=project_id, build_id=build_id)
        assert report.succeeded, report.error

        construccion = (
            await client.get(f"{API}/projects/{project_id}/builds/{build_id}", headers=auth_headers)
        ).json()
        assert construccion["status"] == "succeeded"
        assert construccion["progress"] == 1.0
        assert construccion["artifact_count"] > 30
        assert all(e["status"] in {"succeeded", "skipped"} for e in construccion["stages"])

        # 3. El paquete queda en el almacenamiento y se puede descargar.
        assert construccion["bundle_key"] in storage.keys
        descarga = await client.get(
            f"{API}/projects/{project_id}/builds/{build_id}/download", headers=auth_headers
        )
        assert descarga.status_code == 200
        assert descarga.json()["url"].startswith("memory://")

        # 4. La especificación técnica queda publicada.
        especificacion = (
            await client.get(f"{API}/projects/{project_id}/specification", headers=auth_headers)
        ).json()
        assert {e["name"] for e in especificacion["entities"]} >= {"Member", "Booking"}
        assert especificacion["endpoints"]

        # 5. Despliegue: también se encola y lo resuelve el worker.
        despliegue = await client.post(
            f"{API}/projects/{project_id}/deployments", json={}, headers=auth_headers
        )
        assert despliegue.status_code == 202
        deployment_id = despliegue.json()["id"]

        trabajo = await queue.reserve(timeout_seconds=1)
        assert trabajo is not None and trabajo.kind == DEPLOY_JOB

        await container.deployments.execute_deployment(
            project_id=project_id, deployment_id=deployment_id
        )

        final = (
            await client.get(
                f"{API}/projects/{project_id}/deployments/{deployment_id}",
                headers=auth_headers,
            )
        ).json()
        assert final["status"] == "running"
        assert final["url"].startswith("http://")

        proyecto = (await client.get(f"{API}/projects/{project_id}", headers=auth_headers)).json()
        assert proyecto["status"] == "deployed"
        assert proyecto["live_url"] == final["url"]

        # 6. El progreso se ha publicado en el bus de eventos de principio a fin.
        emitidos = [event.name for event in events.events_for(project_id)]
        assert "build.started" in emitidos
        assert "build.succeeded" in emitidos
        assert "deployment.succeeded" in emitidos

    async def test_no_se_despliega_sin_una_construccion_correcta(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        project_id = await self._proyecto_listo(client, auth_headers)
        response = await client.post(
            f"{API}/projects/{project_id}/deployments", json={}, headers=auth_headers
        )
        assert response.status_code == 404

    async def test_no_se_encolan_dos_construcciones_a_la_vez(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        project_id = await self._proyecto_listo(client, auth_headers)
        assert (
            await client.post(f"{API}/projects/{project_id}/builds", headers=auth_headers)
        ).status_code == 202
        segunda = await client.post(f"{API}/projects/{project_id}/builds", headers=auth_headers)
        assert segunda.status_code == 409

    async def test_los_modulos_no_se_tocan_durante_la_construccion(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        project_id = await self._proyecto_listo(client, auth_headers)
        await client.post(f"{API}/projects/{project_id}/builds", headers=auth_headers)

        response = await client.post(
            f"{API}/projects/{project_id}/modules",
            json={"modules": ["crm"]},
            headers=auth_headers,
        )
        assert response.status_code == 409

    @pytest.mark.parametrize("proveedor", ["docker_local", "vps_ssh", "container_registry"])
    async def test_proveedores_de_despliegue_admitidos(
        self, client: AsyncClient, auth_headers: dict[str, str], proveedor: str
    ) -> None:
        project_id = await self._proyecto_listo(client, auth_headers)
        response = await client.post(
            f"{API}/projects/{project_id}/deployments",
            json={"provider": proveedor},
            headers=auth_headers,
        )
        # Sin construcción previa el proveedor es válido pero no hay nada que desplegar.
        assert response.status_code == 404

    async def test_proveedor_desconocido_se_rechaza(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        project_id = await self._proyecto_listo(client, auth_headers)
        response = await client.post(
            f"{API}/projects/{project_id}/deployments",
            json={"provider": "mi-nube-inventada"},
            headers=auth_headers,
        )
        assert response.status_code == 422
