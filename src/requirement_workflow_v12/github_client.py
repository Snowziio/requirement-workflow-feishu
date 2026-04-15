from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class GitHubError(Exception):
    """Base exception for GitHub API failures."""


class GitHubAuthError(GitHubError):
    """HTTP 401 / 403 from GitHub."""


class GitHubNotFoundError(GitHubError):
    """HTTP 404 from GitHub — repo or file missing."""


class GitHubTransientError(GitHubError):
    """Network timeout, 5xx, or other recoverable failure."""


@dataclass
class FetchedFile:
    content: str
    commit_sha: str


def parse_repo_url(repo_url: str) -> Tuple[str, str]:
    """Parse https://github.com/<owner>/<repo>[.git][/] into (owner, repo)."""
    if not repo_url.startswith("https://github.com/"):
        raise ValueError(f"Not a GitHub HTTPS URL: {repo_url}")
    tail = repo_url[len("https://github.com/"):].strip("/")
    if tail.endswith(".git"):
        tail = tail[: -len(".git")]
    parts = tail.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"Cannot parse owner/repo from: {repo_url}")
    return parts[0], parts[1]


class GitHubClient:
    def __init__(self, token: str, *, timeout: float = 10.0) -> None:
        self._token = token
        self._timeout = timeout

    def fetch_file(self, repo_url: str, path: str, ref: str = "HEAD") -> FetchedFile:
        owner, repo = parse_repo_url(repo_url)
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        if ref and ref != "HEAD":
            url += f"?ref={ref}"
        req = Request(url, headers={
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "requirement-workflow-coordinator",
        })
        try:
            with urlopen(req, timeout=self._timeout) as resp:
                body = resp.read()
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise GitHubAuthError(f"GitHub auth failed ({exc.code})") from exc
            if exc.code == 404:
                raise GitHubNotFoundError(f"{path} not found in {owner}/{repo}") from exc
            if 500 <= exc.code < 600:
                raise GitHubTransientError(f"GitHub {exc.code}") from exc
            raise GitHubError(f"Unexpected GitHub HTTP {exc.code}") from exc
        except URLError as exc:
            raise GitHubTransientError(f"Network error: {exc}") from exc

        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubError("Invalid JSON from GitHub") from exc

        encoding = data.get("encoding")
        if encoding != "base64":
            raise GitHubError(f"Unsupported encoding: {encoding}")
        content_b64 = data.get("content", "")
        try:
            content = base64.b64decode(content_b64).decode("utf-8")
        except Exception as exc:
            raise GitHubError("Failed to decode file content") from exc
        commit_sha = data.get("sha", "")
        if not commit_sha:
            raise GitHubError("GitHub response missing sha")
        return FetchedFile(content=content, commit_sha=commit_sha)
