from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class OnboardingState(str, Enum):
    COLLECTING_REPO = "COLLECTING_REPO"
    COLLECTING_PROJECT_TYPE = "COLLECTING_PROJECT_TYPE"
    COLLECTING_TECH_STACK = "COLLECTING_TECH_STACK"
    WAITING_ARCH_CONFIRMATION = "WAITING_ARCH_CONFIRMATION"
    BOOTSTRAPPING = "BOOTSTRAPPING"
    COMPLETE = "COMPLETE"


@dataclass
class ProjectConfig:
    github_repo_url: str
    is_new_project: bool
    tech_stack: dict[str, str]
    architecture_yaml_initialized: bool = False
    acm_registry_initialized: bool = False
    design_system_doc_id: str | None = None
    onboarding_state: OnboardingState = OnboardingState.COLLECTING_REPO

    @property
    def is_onboarding_complete(self) -> bool:
        return self.onboarding_state == OnboardingState.COMPLETE

    @classmethod
    def from_dict(cls, data: dict) -> ProjectConfig:
        return cls(
            github_repo_url=data["github_repo_url"],
            is_new_project=data.get("is_new_project", True),
            tech_stack=data.get("tech_stack", {}),
            architecture_yaml_initialized=data.get("architecture_yaml_initialized", False),
            acm_registry_initialized=data.get("acm_registry_initialized", False),
            design_system_doc_id=data.get("design_system_doc_id"),
            onboarding_state=OnboardingState(
                data.get("onboarding_state", OnboardingState.COLLECTING_REPO.value)
            ),
        )
