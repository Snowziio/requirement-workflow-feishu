from __future__ import annotations

from dataclasses import dataclass


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
