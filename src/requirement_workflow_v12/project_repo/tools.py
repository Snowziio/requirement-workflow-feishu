"""Layer-3 facade: domain verbs over GitHub primitives.

``ProjectRepoTools`` is the Protocol orchestrators depend on.
``GitHubProjectRepoTools`` is the default implementation that delegates
to ``GitHubGateway``. Errors from the gateway are wrapped in
``ProjectRepoError`` so layer 2 never sees HTTP-level exceptions.
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from ..github_gateway import FileChange, GitHubGateway, GitHubGatewayError
from .architecture_apply import ArchitectureApplyError
from .types import (
    BootstrapRepoResult,
    PlanArtifacts,
    PlanCommitResult,
    PrRef,
    ProjectContext,
    SpecArtifacts,
    SpecMdArtifacts,
    SpecMdCommitResult,
)


_logger = logging.getLogger(__name__)


def _parse_repo(project_repo: str) -> tuple[str, str]:
    """Normalize ``project_repo`` to ``(owner, name)``.

    Accepts shorthand ``owner/name`` and common GitHub URL forms —
    ``https://github.com/owner/name``, the SSH variant, optional ``.git``
    suffix. Bootstrap writes the full URL into Bitable, but gateway
    methods expect shorthand; callers funnel both forms through here.
    """
    s = (project_repo or "").strip()
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    if s.endswith(".git"):
        s = s[: -len(".git")]
    s = s.strip("/")
    parts = s.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError(
            f"invalid project_repo: {project_repo!r}; "
            "expected 'owner/name' or a github URL"
        )
    return parts[0], parts[1]


class ProjectRepoError(RuntimeError):
    """Layer-3 error wrapping a lower-level gateway failure.

    ``recoverable=True`` hints the caller may retry (e.g. transient
    network issues); ``False`` means human intervention is needed.
    """

    def __init__(self, message: str, *, recoverable: bool = False):
        super().__init__(message)
        self.recoverable = recoverable


@runtime_checkable
class ProjectRepoTools(Protocol):
    """Domain-verb facade. Layer 2 depends only on this Protocol."""

    def fetch_project_context(self, project_repo: str) -> ProjectContext: ...

    def commit_spec_artifacts(
        self, req_id: str, artifacts: SpecArtifacts,
    ) -> PrRef: ...

    def commit_plan_artifacts(
        self, artifacts: PlanArtifacts,
    ) -> PlanCommitResult: ...

    def commit_spec_md(
        self, artifacts: SpecMdArtifacts,
    ) -> SpecMdCommitResult: ...

    def cleanup_failed_branch(self, project_repo: str, branch: str) -> None: ...

    def bootstrap_project_repo(
        self,
        *,
        template_owner: str,
        template_repo: str,
        new_owner: str,
        new_name: str,
        populate_files: dict[str, str],
        populate_commit_message: str,
        collaborator_username: str | None,
    ) -> BootstrapRepoResult: ...

    def project_repo_commit(
        self, *, project_repo: str, message: str, files: dict,
    ) -> str: ...

class GitHubProjectRepoTools:
    """Default implementation; delegates to ``GitHubGateway``."""

    def __init__(self, gateway: "GitHubGateway"):
        self._gw = gateway

    def fetch_project_context(self, project_repo: str) -> ProjectContext:
        owner, name = _parse_repo(project_repo)
        short = f"{owner}/{name}"
        try:
            arch_sha, arch_text = self._gw.fetch_file_sha(
                short, "main", "ARCHITECTURE.yaml",
            )
            registry_sha, registry_text = self._gw.fetch_file_sha(
                short, "main", "acm-registry.yaml",
            )
        except GitHubGatewayError as exc:
            raise ProjectRepoError(
                f"fetch_project_context failed for {project_repo}: {exc}",
                recoverable=False,
            ) from exc
        return ProjectContext(
            project_repo=project_repo,
            arch_sha=arch_sha,
            arch_text=arch_text,
            registry_sha=registry_sha,
            registry_text=registry_text,
        )

    def cleanup_failed_branch(self, project_repo: str, branch: str) -> None:
        owner, name = _parse_repo(project_repo)
        short = f"{owner}/{name}"
        try:
            self._gw.delete_branch(short, branch)
        except GitHubGatewayError as exc:
            _logger.warning(
                "cleanup_failed_branch could not delete %s/%s: %s",
                short, branch, exc,
            )

    def commit_spec_artifacts(
        self, req_id: str, artifacts: SpecArtifacts,
    ) -> PrRef:
        owner, name = _parse_repo(artifacts.project_repo)
        short = f"{owner}/{name}"
        try:
            self._gw.create_branch(
                owner=owner, repo=name,
                branch=artifacts.branch, from_branch=artifacts.base_branch,
            )
            head_sha = self._gw.commit_spec_pr_files(
                short, artifacts.branch,
                artifacts.files, artifacts.commit_message,
            )
            pr = self._gw.open_pull_request(
                owner=owner, repo=name,
                head_branch=artifacts.branch, base_branch=artifacts.base_branch,
                title=artifacts.pr_title, body=artifacts.pr_body,
            )
        except GitHubGatewayError as exc:
            self.cleanup_failed_branch(short, artifacts.branch)
            raise ProjectRepoError(
                f"commit_spec_artifacts failed for {req_id}: {exc}",
                recoverable=False,
            ) from exc
        return PrRef(
            number=int(pr["number"]),
            html_url=str(pr["html_url"]),
            head_sha=head_sha,
            branch=artifacts.branch,
        )

    def commit_plan_artifacts(
        self, artifacts: PlanArtifacts,
    ) -> PlanCommitResult:
        from ..project_context_apply import (
            ProjectContextApplyError,
            apply_project_context_change,
        )
        owner, name = _parse_repo(artifacts.project_repo)
        short = f"{owner}/{name}"
        plan_path = f"docs/specs/{artifacts.req_id}/plan.md"
        files_to_commit = [
            FileChange(path=plan_path, content=artifacts.plan_md_content),
        ]
        architecture_updated = False

        if artifacts.project_context_change is not None:
            arch_path = "docs/ARCHITECTURE.md"
            try:
                _arch_sha, arch_text = self._gw.fetch_file_sha(
                    short, "main", arch_path,
                )
            except GitHubGatewayError as exc:
                raise ProjectRepoError(
                    f"commit_plan_artifacts: cannot fetch {arch_path}: {exc}",
                    recoverable=False,
                ) from exc
            try:
                updated_files = apply_project_context_change(
                    original_files={arch_path: arch_text},
                    change=artifacts.project_context_change,
                )
            except ProjectContextApplyError as exc:
                recoverable = isinstance(exc.__cause__, ArchitectureApplyError) and exc.__cause__.recoverable
                raise ProjectRepoError(
                    f"commit_plan_artifacts: project_context_change apply failed: {exc}",
                    recoverable=recoverable,
                ) from exc
            new_arch = updated_files.get(arch_path)
            if new_arch is not None and new_arch != arch_text:
                files_to_commit.append(
                    FileChange(path=arch_path, content=new_arch),
                )
                architecture_updated = True

        try:
            sha = self._gw.commit_files(
                owner=owner, repo=name, branch="main",
                files=files_to_commit, message=artifacts.commit_message,
            )
        except GitHubGatewayError as exc:
            raise ProjectRepoError(
                f"commit_plan_artifacts: commit to main failed: {exc}",
                recoverable=False,
            ) from exc
        return PlanCommitResult(
            commit_sha=sha, branch="main",
            plan_md_path=plan_path,
            architecture_updated=architecture_updated,
        )

    def commit_spec_md(
        self, artifacts: SpecMdArtifacts,
    ) -> SpecMdCommitResult:
        """Freeze the 9-section spec.md from Feishu into GitHub on main.

        Mirrors ``commit_plan_artifacts`` but writes a single file
        ``docs/specs/<req_id>/spec.md``. No project_context_change path —
        architecture freezes with plan.
        """
        owner, name = _parse_repo(artifacts.project_repo)
        spec_path = f"docs/specs/{artifacts.req_id}/spec.md"
        try:
            sha = self._gw.commit_files(
                owner=owner, repo=name, branch="main",
                files=[FileChange(path=spec_path, content=artifacts.spec_md_content)],
                message=artifacts.commit_message,
            )
        except GitHubGatewayError as exc:
            raise ProjectRepoError(
                f"commit_spec_md: commit to main failed: {exc}",
                recoverable=False,
            ) from exc
        return SpecMdCommitResult(
            commit_sha=sha, branch="main", spec_md_path=spec_path,
        )

    def project_repo_commit(
        self, *, project_repo: str, message: str, files: dict,
    ) -> str:
        """Atomically commit a dict of ``{repo_path: content_bytes_or_str}`` to main.

        Generic multi-file commit helper used by ``DesignSyncer``. Mirrors
        ``commit_plan_artifacts``'s internal pattern but without the plan /
        ARCHITECTURE coupling — just a flat files map.

        Non-UTF-8 bytes (e.g. binary bundle.zip) are skipped with a warning,
        since ``FileChange.content`` requires text in this iteration.

        Returns the commit SHA.
        """
        owner, name = _parse_repo(project_repo)
        file_changes = []
        for path, content in files.items():
            try:
                text = (
                    content.decode("utf-8") if isinstance(content, (bytes, bytearray))
                    else content
                )
            except UnicodeDecodeError:
                _logger.warning(
                    "project_repo_commit: skipping non-UTF-8 file %s "
                    "(binary content not supported in MVP)",
                    path,
                )
                continue
            file_changes.append(FileChange(path=path, content=text))
        try:
            sha = self._gw.commit_files(
                owner=owner, repo=name, branch="main",
                files=file_changes, message=message,
            )
        except GitHubGatewayError as exc:
            raise ProjectRepoError(
                f"project_repo_commit: commit to main failed: {exc}",
                recoverable=False,
            ) from exc
        return sha

    def read_project_file(
        self,
        project_repo: str,
        path: str,
        *,
        branch: str = "main",
        default: str | None = None,
    ) -> str:
        """Read a file's text content from a project repo.

        If the file is missing on the remote:
        - returns ``default`` when provided
        - raises ``ProjectRepoError`` otherwise

        Used by DesignSyncer to hydrate design/PAGES.yaml + design/INDEX.md on
        fresh coordinator containers — those files exist in the GitHub repo
        (written by Bootstrap at project creation) but not on the coordinator's
        local filesystem, since coordinator doesn't clone the project repo.
        """
        owner, name = _parse_repo(project_repo)
        short = f"{owner}/{name}"
        try:
            _sha, text = self._gw.fetch_file_sha(short, branch, path)
            return text
        except GitHubGatewayError as exc:
            if default is not None:
                _logger.info(
                    "read_project_file: %s:%s not found on %s; using default",
                    short, path, branch,
                )
                return default
            raise ProjectRepoError(
                f"read_project_file failed for {short}:{path}: {exc}",
                recoverable=False,
            ) from exc

    def bootstrap_project_repo(
        self,
        *,
        template_owner: str,
        template_repo: str,
        new_owner: str,
        new_name: str,
        populate_files: dict[str, str],
        populate_commit_message: str,
        collaborator_username: str | None,
    ) -> BootstrapRepoResult:
        try:
            existing = self._gw.get_repo(owner=new_owner, name=new_name)
            if existing is None:
                html_url = self._gw.create_repo_from_template(
                    template_owner=template_owner,
                    template_repo=template_repo,
                    owner=new_owner,
                    name=new_name,
                    private=True,
                    description=f"Bootstrapped project {new_name}",
                )
                default_branch = "main"
                # /generate returns 201 before the initial commit is visible;
                # subsequent git-data calls see 409 "Git Repository is empty".
                self._gw.wait_for_branch_ready(new_owner, new_name, default_branch)
            else:
                html_url = str(existing["html_url"])
                default_branch = str(existing.get("default_branch", "main"))

            file_changes = [
                FileChange(path=p, content=c) for p, c in populate_files.items()
            ]
            populate_sha = self._gw.commit_files(
                owner=new_owner,
                repo=new_name,
                branch=default_branch,
                files=file_changes,
                message=populate_commit_message,
            )

            if collaborator_username:
                self._gw.add_collaborator(
                    owner=new_owner,
                    name=new_name,
                    username=collaborator_username,
                    permission="push",
                )
        except GitHubGatewayError as exc:
            raise ProjectRepoError(
                f"bootstrap_project_repo failed for {new_owner}/{new_name}: {exc}",
                recoverable=False,
            ) from exc
        return BootstrapRepoResult(
            html_url=html_url,
            default_branch=default_branch,
            initial_populate_commit_sha=populate_sha,
        )
