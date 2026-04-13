#!/usr/bin/env python3
"""
Path B bootstrap script: scan existing GitHub repo and generate ARCHITECTURE.yaml.

Usage:
    python scripts/bootstrap_architecture.py --repo https://github.com/org/repo [--branch main] [--token TOKEN]

Requires ANTHROPIC_API_KEY and GITHUB_TOKEN env vars (or --token flag).
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

try:
    from github import Github
except ImportError:
    print("ERROR: PyGithub not installed. Run: pip install PyGithub")
    sys.exit(1)

SYSTEM_PROMPT = """\
You are a technical architect. Given a GitHub repository's directory tree and key file excerpts,
generate an ARCHITECTURE.yaml file following this exact schema:

version: "YYYY-MM-DD"
project: {project_name}

tech_stack:
  language: ...
  framework: ...
  database: ...
  test_framework: ...

services:
  - name: ...
    description: ...
    repo_path: ...
    public_interfaces:
      - method: GET/POST/PUT/DELETE
        path: /api/...
        introduced_in: UNKNOWN

modules:
  - name: ...
    description: ...
    repo_path: ...
    public_api:
      - function: ...
        input: "..."
        output: "..."
    status: stable

data_models:
  - name: ...
    description: ...
    columns:
      id: "UUID, primary key"

external_dependencies: []

Only include what you can confidently infer from the code. Leave lists empty if uncertain.
Output ONLY the YAML, no explanation.
"""


def get_repo_context(repo, branch: str) -> str:
    """Fetch directory tree + key file excerpts."""
    lines = []
    try:
        contents = repo.get_contents("", ref=branch)
        tree_items = []
        while contents:
            item = contents.pop(0)
            tree_items.append(item.path)
            if item.type == "dir" and item.path.count("/") < 2:
                contents.extend(repo.get_contents(item.path, ref=branch))
        lines.append("## Directory Tree\n" + "\n".join(tree_items[:150]))
    except Exception as e:
        lines.append(f"## Directory Tree\nError: {e}")

    # Try to read key files
    key_paths = ["README.md", "pyproject.toml", "requirements.txt", "package.json"]
    for path in key_paths:
        try:
            f = repo.get_contents(path, ref=branch)
            text = f.decoded_content.decode("utf-8", errors="replace")[:2000]
            lines.append(f"## {path}\n{text}")
        except Exception:
            pass

    return "\n\n".join(lines)


def generate_architecture_yaml(repo_context: str, project_name: str) -> str:
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Project name: {project_name}\n\n{repo_context}",
        }],
    )
    return message.content[0].text.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ARCHITECTURE.yaml from existing GitHub repo")
    parser.add_argument("--repo", required=True, help="GitHub repo URL (https://github.com/org/repo)")
    parser.add_argument("--branch", default="main", help="Branch to scan (default: main)")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""), help="GitHub token")
    parser.add_argument("--output", default="ARCHITECTURE.yaml", help="Output file path")
    args = parser.parse_args()

    github_token = args.token or os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        print("ERROR: GitHub token required. Set GITHUB_TOKEN env var or use --token")
        sys.exit(1)

    repo_path = args.repo.rstrip("/").removeprefix("https://github.com/")
    project_name = repo_path.split("/")[-1]

    print(f"Scanning repo: {args.repo} (branch: {args.branch})")
    g = Github(github_token)
    repo = g.get_repo(repo_path)

    print("Fetching repository context...")
    context = get_repo_context(repo, args.branch)

    print("Generating ARCHITECTURE.yaml with Claude...")
    yaml_content = generate_architecture_yaml(context, project_name)

    print("\n--- Generated ARCHITECTURE.yaml ---")
    print(yaml_content)
    print("-----------------------------------\n")

    confirm = input("Commit this to GitHub? [y/N] ").strip().lower()
    if confirm != "y":
        # Save locally
        with open(args.output, "w") as f:
            f.write(yaml_content)
        print(f"Saved locally to {args.output}. Review and commit manually.")
        return

    try:
        existing = repo.get_contents("ARCHITECTURE.yaml", ref=args.branch)
        repo.update_file(
            path="ARCHITECTURE.yaml",
            message="chore: update ARCHITECTURE.yaml (bootstrap from existing codebase)",
            content=yaml_content,
            sha=existing.sha,
            branch=args.branch,
        )
        print("Updated ARCHITECTURE.yaml in GitHub.")
    except Exception:
        repo.create_file(
            path="ARCHITECTURE.yaml",
            message="chore: initialize ARCHITECTURE.yaml (bootstrap from existing codebase)",
            content=yaml_content,
            branch=args.branch,
        )
        print("Created ARCHITECTURE.yaml in GitHub.")

    print("Done. You can now reply 「初始化完成」 in the Feishu creation group.")


if __name__ == "__main__":
    main()
