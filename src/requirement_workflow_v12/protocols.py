from __future__ import annotations

from dataclasses import dataclass, field

@dataclass
class CreationRequest:
    project: str
    name: str
    summary: str
    creator: str
    creator_user_id: str
    creation_chat_id: str


@dataclass
class CreationResponse:
    req_id: str
    project_group_id: str
    message_to_creation_group: str
    message_to_project_group: str
    author_start_command: str


@dataclass
class AuthorStartBinding:
    req_id: str
    author_dm_chat_id: str
    user_id: str


@dataclass
class AuthorStartResponse:
    accepted: bool
    message: str
    active_req_id: str | None = None


@dataclass
class CreationFormPayload:
    project: str
    name: str
    summary: str
    creator: str
    creator_user_id: str
    creation_chat_id: str
    background_links: str = ""
    priority: str = ""
    expected_due_date: str = ""
    needs_ui: bool = False
    category: str = ""


@dataclass
class ProjectCreationFormPayload:
    project: str
    category: str
    owner_user_id: str
    creator_chat_id: str
    display_name: str = ""
    brief: str = ""
    github_username: str = ""
    tech_stack: str = ""


@dataclass
class AgentAuthorEventPayload:
    req_id: str
    event: str
    summary: str
    document_url: str = ""
    document_version: str = ""
    iteration_round: int | None = None
    completed_fields: list[str] = field(default_factory=list)


@dataclass
class AgentReviewEventPayload:
    req_id: str
    event: str
    review_summary: str
    review_notes_url: str = ""
    document_url: str = ""
    review_result: str = ""


@dataclass
class AgentRequirementContextQuery:
    req_id: str


@dataclass
class AgentSpecEventPayload:
    req_id: str
    event: str  # "spec_start" | "spec_submit"
    summary: str
    spec_document_url: str = ""
