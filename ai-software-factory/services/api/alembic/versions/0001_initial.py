"""Esquema inicial de la plataforma.

Revision ID: 0001_initial
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("max_projects", sa.Integer, nullable=False, server_default="100"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("role", sa.String(20), nullable=False, server_default="developer"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_organization_id", "users", ["organization_id"])

    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("prompt", sa.Text, nullable=False, server_default=""),
        sa.Column("business_domain", sa.String(40), nullable=False, server_default="generic"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("tech_stack", sa.JSON, nullable=False),
        sa.Column("module_keys", sa.JSON, nullable=False),
        sa.Column("live_url", sa.String(500), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])
    op.create_index("ix_projects_slug", "projects", ["slug"])
    op.create_index("ix_projects_status", "projects", ["status"])
    op.create_index("ix_projects_org_status", "projects", ["organization_id", "status"])

    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("pending_questions", sa.JSON, nullable=False),
        sa.Column("answers", sa.JSON, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_conversations_project_id", "conversations", ["project_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("metadata", sa.JSON, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])

    op.create_table(
        "requirements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("business_domain", sa.String(40), nullable=False, server_default="generic"),
        sa.Column("stories", sa.JSON, nullable=False),
        sa.Column("constraints", sa.JSON, nullable=False),
        sa.Column("out_of_scope", sa.JSON, nullable=False),
        sa.Column("suggested_modules", sa.JSON, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_requirements_project_id", "requirements", ["project_id"])
    op.create_index("ix_requirements_created_at", "requirements", ["created_at"])

    op.create_table(
        "specifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requirements_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("tech_stack", sa.JSON, nullable=False),
        sa.Column("entities", sa.JSON, nullable=False),
        sa.Column("endpoints", sa.JSON, nullable=False),
        sa.Column("modules", sa.JSON, nullable=False),
        sa.Column("pages", sa.JSON, nullable=False),
        sa.Column("notes", sa.JSON, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_specifications_project_id", "specifications", ["project_id"])
    op.create_index("ix_specifications_created_at", "specifications", ["created_at"])

    op.create_table(
        "builds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("specification_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Float, nullable=False, server_default="0"),
        sa.Column("stages", sa.JSON, nullable=False),
        sa.Column("artifacts", sa.JSON, nullable=False),
        sa.Column("bundle_key", sa.String(500), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_builds_project_id", "builds", ["project_id"])
    op.create_index("ix_builds_status", "builds", ["status"])
    op.create_index("ix_builds_created_at", "builds", ["created_at"])

    op.create_table(
        "deployments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("build_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False, server_default="docker_local"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("image_tag", sa.String(300), nullable=True),
        sa.Column("env", sa.JSON, nullable=False),
        sa.Column("logs", sa.JSON, nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_deployments_project_id", "deployments", ["project_id"])
    op.create_index("ix_deployments_build_id", "deployments", ["build_id"])
    op.create_index("ix_deployments_status", "deployments", ["status"])
    op.create_index("ix_deployments_created_at", "deployments", ["created_at"])

    op.create_table(
        "module_installations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("module_key", sa.String(64), nullable=False),
        sa.Column("version", sa.String(20), nullable=False, server_default="1.0.0"),
        sa.Column("state", sa.String(20), nullable=False, server_default="installed"),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column(
            "installed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_module_installations_project_id", "module_installations", ["project_id"])
    op.create_index("ix_module_installations_module_key", "module_installations", ["module_key"])
    op.create_index(
        "ix_module_installations_project_key",
        "module_installations",
        ["project_id", "module_key"],
        unique=True,
    )


def downgrade() -> None:
    for table in (
        "module_installations",
        "deployments",
        "builds",
        "specifications",
        "requirements",
        "messages",
        "conversations",
        "projects",
        "users",
        "organizations",
    ):
        op.drop_table(table)
