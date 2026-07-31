"""Los once agentes especializados de la fábrica."""

from factory.agents.specialists.analyst import RequirementsAnalyst
from factory.agents.specialists.api import ApiDesigner
from factory.agents.specialists.architect import SoftwareArchitect
from factory.agents.specialists.backend import BackendGenerator
from factory.agents.specialists.database import DatabaseDesigner
from factory.agents.specialists.deployment import DeploymentAgent
from factory.agents.specialists.docs import DocumentationGenerator
from factory.agents.specialists.frontend import FrontendGenerator
from factory.agents.specialists.maintenance import MaintenanceAgent
from factory.agents.specialists.reviewer import CodeReviewer
from factory.agents.specialists.testing import TestGenerator

__all__ = [
    "ApiDesigner",
    "BackendGenerator",
    "CodeReviewer",
    "DatabaseDesigner",
    "DeploymentAgent",
    "DocumentationGenerator",
    "FrontendGenerator",
    "MaintenanceAgent",
    "RequirementsAnalyst",
    "SoftwareArchitect",
    "TestGenerator",
]
