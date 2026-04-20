"""GitHub gateway for Coordinator-driven repo / branch / commit / PR ops.

Used in SPEC_TRANSFORMING to materialize spec-transformer's four-file
output into a Spec PR. The transformer agents themselves never touch
GitHub — all I/O lives here, behind the Coordinator.

Auth: classic PAT via ``Settings.github_token``. App-based auth deferred
until multi-org / multi-customer phase.
"""
from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from typing import Iterable

try:  # pragma: no cover - optional during tests before runtime deps installed
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

from .config import Settings


logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


class GitHubGatewayError(RuntimeError):
    """Raised on non-2xx GitHub API responses."""

    def __init__(self, status: int, message: str, payload: object | None = None):
        super().__init__(f"github api {status}: {message}")
        self.status = status
        self.payload = payload


@dataclass(frozen=True)
class FileChange:
    """One file to include in an atomic multi-file commit."""

    path: str
    content: str  # plain text; binary not supported in this iteration


class GitHubGateway:
    """Thin GitHub REST client. One HTTP call = one method.

    Multi-file commits go through the Git Data API (blob → tree → commit
    → ref) so transformer's four files land as a single commit.
    """

    def __init__(self, settings: Settings, *, client: "httpx.Client | None" = None):
        if not settings.github_token:
            raise ValueError("Settings.github_token is required for GitHubGateway")
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.Client(
            base_url=GITHUB_API_BASE,
            timeout=30.0,
            headers={
                "Authorization": f"token {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "requirement-workflow-coordinator",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "GitHubGateway":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- repo / branch ------------------------------------------------

    def create_repo_from_template(
        self,
        *,
        template_owner: str,
        template_repo: str,
        owner: str,
        name: str,
        private: bool = True,
        description: str = "",
    ) -> str:
        """POST /repos/{template_owner}/{template_repo}/generate. Returns html_url."""
        body = {
            "owner": owner,
            "name": name,
            "private": private,
            "description": description,
            "include_all_branches": False,
        }
        resp = self.client.post(
            f"/repos/{template_owner}/{template_repo}/generate", json=body
        )
        data = self._unwrap(resp)
        return str(data["html_url"])

    def get_repo(self, *, owner: str, name: str) -> dict | None:
        """GET /repos/{owner}/{name}. Returns metadata dict, or None on 404."""
        resp = self.client.get(f"/repos/{owner}/{name}")
        if resp.status_code == 404:
            return None
        data = self._unwrap(resp)
        return dict(data)

    def add_collaborator(
        self, *, owner: str, name: str, username: str, permission: str = "push"
    ) -> None:
        """PUT /repos/{owner}/{name}/collaborators/{username}. 201/204 indicate success."""
        resp = self.client.put(
            f"/repos/{owner}/{name}/collaborators/{username}",
            json={"permission": permission},
        )
        if resp.status_code not in (201, 204):
            raise GitHubGatewayError(
                resp.status_code, f"add_collaborator failed: {resp.text}"
            )

    def create_branch(
        self, *, owner: str, repo: str, branch: str, from_branch: str | None = None
    ) -> str:
        """Create ``branch`` pointing at the head of ``from_branch``. Returns new ref SHA."""
        base = from_branch or self.settings.github_default_branch
        head_sha = self._get_branch_head_sha(owner, repo, base)
        resp = self.client.post(
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": head_sha},
        )
        data = self._unwrap(resp)
        return str(data["object"]["sha"])

    # --- commit + PR --------------------------------------------------

    def commit_files(
        self,
        *,
        owner: str,
        repo: str,
        branch: str,
        files: Iterable[FileChange],
        message: str,
    ) -> str:
        """Create a single commit on ``branch`` containing all ``files``. Returns commit SHA.

        Uses Git Data API so the four-file payload lands atomically.
        """
        files = list(files)
        if not files:
            raise ValueError("commit_files requires at least one FileChange")

        parent_sha = self._get_branch_head_sha(owner, repo, branch)
        parent_commit = self._unwrap(
            self.client.get(f"/repos/{owner}/{repo}/git/commits/{parent_sha}")
        )
        base_tree_sha = parent_commit["tree"]["sha"]

        tree_entries = []
        for fc in files:
            blob = self._unwrap(
                self.client.post(
                    f"/repos/{owner}/{repo}/git/blobs",
                    json={
                        "content": base64.b64encode(fc.content.encode("utf-8")).decode("ascii"),
                        "encoding": "base64",
                    },
                )
            )
            tree_entries.append(
                {"path": fc.path, "mode": "100644", "type": "blob", "sha": blob["sha"]}
            )

        new_tree = self._unwrap(
            self.client.post(
                f"/repos/{owner}/{repo}/git/trees",
                json={"base_tree": base_tree_sha, "tree": tree_entries},
            )
        )
        new_commit = self._unwrap(
            self.client.post(
                f"/repos/{owner}/{repo}/git/commits",
                json={
                    "message": message,
                    "tree": new_tree["sha"],
                    "parents": [parent_sha],
                },
            )
        )
        commit_sha = str(new_commit["sha"])
        self._unwrap(
            self.client.patch(
                f"/repos/{owner}/{repo}/git/refs/heads/{branch}",
                json={"sha": commit_sha, "force": False},
            )
        )
        return commit_sha

    def commit_spec_pr_files(
        self,
        repo: str,
        branch: str,
        files: dict[str, str],
        message: str,
    ) -> str:
        """Atomic multi-file commit on ``branch`` for a Spec PR. Returns new commit sha.

        Semantic wrapper over :meth:`commit_files` — callers express intent
        that this is the Spec PR four-file commit. ``repo`` is ``"owner/repo"``;
        ``files`` maps path → text content.
        """
        owner, repo_name = repo.split("/", 1)
        file_changes = [FileChange(path=p, content=c) for p, c in files.items()]
        return self.commit_files(
            owner=owner,
            repo=repo_name,
            branch=branch,
            files=file_changes,
            message=message,
        )

    def open_pull_request(
        self,
        *,
        owner: str,
        repo: str,
        head_branch: str,
        base_branch: str | None = None,
        title: str,
        body: str = "",
    ) -> dict:
        """POST /repos/{owner}/{repo}/pulls. Returns {number, html_url}."""
        base = base_branch or self.settings.github_default_branch
        resp = self.client.post(
            f"/repos/{owner}/{repo}/pulls",
            json={"title": title, "head": head_branch, "base": base, "body": body},
        )
        data = self._unwrap(resp)
        return {"number": int(data["number"]), "html_url": str(data["html_url"])}

    def delete_branch(self, repo: str, branch: str) -> None:
        """DELETE /repos/{owner}/{repo}/git/refs/heads/{branch}.

        Idempotent: 204 (success), 404 (already gone), and 422 (stale ref)
        are all treated as success. Any other non-2xx raises GitHubGatewayError.
        ``repo`` is ``"owner/repo"``.
        """
        owner, repo_name = repo.split("/", 1)
        resp = self.client.delete(f"/repos/{owner}/{repo_name}/git/refs/heads/{branch}")
        if resp.status_code not in (204, 404, 422):
            self._unwrap(resp)

    # --- file contents -----------------------------------------------

    def fetch_file_sha(self, repo: str, ref: str, path: str) -> tuple[str, str]:
        """Return (sha, decoded_text) for a file via Contents API.

        ``repo`` is ``"owner/repo"``. ``ref`` may be a branch, tag, or commit SHA.
        Raises ``GitHubGatewayError`` on non-2xx responses.
        """
        owner, repo_name = repo.split("/", 1)
        data = self._unwrap(
            self.client.get(
                f"/repos/{owner}/{repo_name}/contents/{path}",
                params={"ref": ref},
            )
        )
        text = base64.b64decode(data["content"]).decode("utf-8")
        return str(data["sha"]), text

    # --- internals ----------------------------------------------------

    def _get_branch_head_sha(self, owner: str, repo: str, branch: str) -> str:
        data = self._unwrap(
            self.client.get(f"/repos/{owner}/{repo}/git/refs/heads/{branch}")
        )
        return str(data["object"]["sha"])

    def wait_for_branch_ready(
        self,
        owner: str,
        repo: str,
        branch: str,
        *,
        timeout_s: float = 30.0,
        interval_s: float = 2.0,
        sleep=time.sleep,
        clock=time.monotonic,
    ) -> str:
        """Poll `/git/refs/heads/{branch}` until it resolves to a commit SHA.

        Needed after `/repos/{owner}/{repo}/generate`: GitHub returns 201 on
        the template-generate call but takes a few seconds to propagate the
        initial commit, during which `refs/heads/main` returns 409 "Git
        Repository is empty" or 404.

        Swallows those two transient statuses; any other error propagates.
        Returns the resolved head SHA.
        """
        deadline = clock() + timeout_s
        last_error: GitHubGatewayError | None = None
        while True:
            try:
                return self._get_branch_head_sha(owner, repo, branch)
            except GitHubGatewayError as exc:
                if exc.status not in (404, 409):
                    raise
                last_error = exc
            if clock() >= deadline:
                assert last_error is not None
                raise last_error
            sleep(interval_s)

    @staticmethod
    def _unwrap(resp: "httpx.Response") -> dict:
        if resp.status_code >= 400:
            try:
                payload = resp.json()
                msg = payload.get("message", resp.text)
            except Exception:
                payload = None
                msg = resp.text
            raise GitHubGatewayError(resp.status_code, msg, payload)
        return resp.json() if resp.content else {}
