"""Domain types for the project bootstrap orchestrator."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class BootstrapStep(IntEnum):
    VALIDATE = 1
    UPSERT_CONFIG = 2
    CREATE_REPO = 3
    POPULATE_MAIN = 4
    CREATE_ARCHITECTURE_DOC = 5
    CREATE_FEISHU_GROUP = 6
    FINALIZE = 7


@dataclass(frozen=True)
class BootstrapRequest:
    project: str
    category: str
    owner_user_id: str
    creator_chat_id: str
    github_username: str | None = None
    resume: bool = False
    architecture_seed: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BootstrapResult:
    project: str
    github_repo_url: str
    architecture_doc_id: str
    architecture_doc_url: str
    feishu_chat_id: str
    template_version: str


class BootstrapStepError(RuntimeError):
    """Raised when a single Bootstrap step fails.

    The ``step`` field lets the service record which step failed in
    ``bootstrap_log`` so ``--resume`` can continue from the next step.
    """

    def __init__(self, *, step: BootstrapStep, message: str):
        super().__init__(f"Bootstrap step {step.value} ({step.name}): {message}")
        self.step = step
        self.message = message
