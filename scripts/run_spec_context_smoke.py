#!/usr/bin/env python3
"""Local smoke test for /queries/openclaw/spec-context.

Invokes send_openclaw_callback.py spec-context against a running Coordinator
and validates that the response carries the fields spec-author depends on.

Usage:
    python3 scripts/run_spec_context_smoke.py --req-id REQ-XXX
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REQUIRED_CONTEXT_FIELDS = (
    "req_id",
    "status",
    "needs_ui",
    "requirement_document_url",
    "architecture_yaml",
    "architecture_commit_sha",
    "github_repo_url",
)

SCRIPT_DIR = Path(__file__).resolve().parent
CALLBACK_CLI = SCRIPT_DIR / "send_openclaw_callback.py"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--req-id", required=True)
    parser.add_argument("--base-url", default=os.environ.get("COORDINATOR_BASE_URL", "http://127.0.0.1:8004"))
    parser.add_argument("--secret", default=os.environ.get("OPENCLAW_CALLBACK_SECRET", ""))
    args = parser.parse_args()

    cmd = [
        sys.executable,
        str(CALLBACK_CLI),
        "--base-url",
        args.base_url,
        "--secret",
        args.secret,
        "--req-id",
        args.req_id,
        "spec-context",
    ]
    print(f"[smoke] $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        print(f"[smoke] FAIL: CLI exit {result.returncode}", file=sys.stderr)
        return result.returncode

    try:
        body = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        print(f"[smoke] FAIL: response is not JSON ({exc})", file=sys.stderr)
        return 2

    if not body.get("ok"):
        print(f"[smoke] FAIL: ok != true in response", file=sys.stderr)
        return 3

    context = body.get("context") or {}
    missing = [k for k in REQUIRED_CONTEXT_FIELDS if k not in context]
    if missing:
        print(f"[smoke] FAIL: context missing fields {missing}", file=sys.stderr)
        return 4

    if not body.get("context_token"):
        print(f"[smoke] FAIL: missing context_token", file=sys.stderr)
        return 5

    print(
        f"[smoke] OK: status={context['status']} "
        f"sha={context['architecture_commit_sha'][:8]} "
        f"token={body['context_token'][:24]}..."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
