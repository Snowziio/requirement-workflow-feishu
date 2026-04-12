#!/usr/bin/env python3

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from send_openclaw_callback import (
    AUTHOR_ENDPOINT,
    CONTEXT_QUERY_ENDPOINT,
    DEFAULT_COORDINATOR_BASE_URL,
    REVIEW_ENDPOINT,
    post_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a minimal OpenClaw -> Coordinator smoke flow for a single requirement."
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Coordinator base URL. Defaults to $COORDINATOR_BASE_URL or http://127.0.0.1:8004",
    )
    parser.add_argument("--secret", default="", help="Optional callback signing secret. Defaults to $OPENCLAW_CALLBACK_SECRET")
    parser.add_argument("--req-id", required=True, help="Requirement ID, e.g. REQ-HARNESS-001")
    parser.add_argument("--document-url", default="", help="Optional requirement document URL to write back in events")
    parser.add_argument("--review-notes-url", default="", help="Optional review notes URL for reviewer events")
    parser.add_argument("--document-version", default="", help="Optional document version label for author event")
    parser.add_argument("--iteration-round", type=int, default=None, help="Optional iteration round for author event")
    parser.add_argument(
        "--review-event",
        default="review_ready_for_human_confirmation",
        choices=[
            "review_returned_for_revision",
            "review_ready_for_human_confirmation",
            "human_confirmed",
            "human_rejected",
            "final_review_passed",
            "final_review_rejected",
        ],
        help="Reviewer event to send after author-ready",
    )
    parser.add_argument(
        "--skip-author",
        action="store_true",
        help="Skip author_ready_for_ai_review and only fetch context plus optional reviewer event",
    )
    parser.add_argument(
        "--skip-review",
        action="store_true",
        help="Skip reviewer event and only fetch context plus optional author-ready",
    )
    parser.add_argument(
        "--author-summary",
        default="author 已完成当前轮需求文档撰写，可进入 AI review。",
        help="Summary used for author_ready_for_ai_review",
    )
    parser.add_argument(
        "--review-summary",
        default="AI review 已完成，当前流程可继续推进。",
        help="Summary used for the reviewer event",
    )
    parser.add_argument(
        "--review-result",
        default="ai_ready",
        help="Optional review_result field for reviewer event",
    )
    return parser


def run_step(
    label: str,
    url: str,
    payload: Dict[str, Any],
    secret: Optional[str],
) -> Tuple[int, bool]:
    print("=== {} ===".format(label))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    exit_code = post_json(url, payload, secret)
    print("")
    return exit_code, exit_code == 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    base_url = (args.base_url or os.environ.get("COORDINATOR_BASE_URL") or DEFAULT_COORDINATOR_BASE_URL).rstrip("/")
    secret = args.secret or os.environ.get("OPENCLAW_CALLBACK_SECRET") or None

    steps: List[Tuple[str, str, Dict[str, Any]]] = [
        (
            "fetch-context",
            "{}{}".format(base_url, CONTEXT_QUERY_ENDPOINT),
            {"req_id": args.req_id},
        )
    ]

    if not args.skip_author:
        steps.append(
            (
                "author-ready",
                "{}{}".format(base_url, AUTHOR_ENDPOINT),
                {
                    "req_id": args.req_id,
                    "event": "author_ready_for_ai_review",
                    "summary": args.author_summary,
                    "document_url": args.document_url or "",
                    "document_version": args.document_version or "",
                    "iteration_round": args.iteration_round,
                },
            )
        )

    if not args.skip_review:
        steps.append(
            (
                "review-event",
                "{}{}".format(base_url, REVIEW_ENDPOINT),
                {
                    "req_id": args.req_id,
                    "event": args.review_event,
                    "review_summary": args.review_summary,
                    "review_notes_url": args.review_notes_url or "",
                    "document_url": args.document_url or "",
                    "review_result": args.review_result or "",
                },
            )
        )

    has_failure = False
    for label, url, payload in steps:
        exit_code, ok = run_step(label, url, payload, secret)
        if not ok:
            has_failure = True
            print("step_failed={} exit_code={}".format(label, exit_code), file=sys.stderr)
            break

    return 1 if has_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
