#!/usr/bin/env python3

import argparse
import hashlib
import hmac
import json
import sys
import time
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


AUTHOR_ENDPOINT = "/callbacks/openclaw/author-turn"
REVIEW_ENDPOINT = "/callbacks/openclaw/review-result"
CONTEXT_QUERY_ENDPOINT = "/queries/openclaw/requirement-context"


def build_signature(secret: str, timestamp: str, raw_body: bytes) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()


def build_author_payload(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "req_id": args.req_id,
        "event": "author_ready_for_ai_review",
        "summary": args.summary,
        "document_url": args.document_url or "",
        "document_version": args.document_version or "",
        "iteration_round": args.iteration_round,
    }


def build_review_payload(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "req_id": args.req_id,
        "event": args.event,
        "review_summary": args.summary,
        "review_notes_url": args.review_notes_url or "",
        "document_url": args.document_url or "",
        "review_result": args.review_result or "",
    }


def build_context_query_payload(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "req_id": args.req_id,
    }


def post_json(url: str, payload: Dict[str, Any], secret: Optional[str]) -> int:
    raw_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret:
        timestamp = str(int(time.time()))
        headers["X-OpenClaw-Timestamp"] = timestamp
        headers["X-OpenClaw-Signature"] = build_signature(secret, timestamp, raw_body)

    request = Request(url, data=raw_body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            print(body)
            return 0
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(body or str(exc), file=sys.stderr)
        return exc.code or 1
    except URLError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send an OpenClaw workflow event callback to Coordinator Service.")
    parser.add_argument("--base-url", required=True, help="Coordinator base URL, e.g. https://coordinator.example.com")
    parser.add_argument("--secret", default="", help="Optional callback signing secret")
    parser.add_argument("--req-id", required=True, help="Requirement ID, e.g. REQ-HARNESS-001")

    subparsers = parser.add_subparsers(dest="mode")

    author_parser = subparsers.add_parser("author-ready", help="Send author_ready_for_ai_review")
    author_parser.add_argument("--summary", required=True, help="Event summary for Coordinator/Bitable")
    author_parser.add_argument("--document-url", default="", help="Current requirement document URL")
    author_parser.add_argument("--document-version", default="", help="Optional document version label")
    author_parser.add_argument("--iteration-round", type=int, default=None, help="Optional document iteration round")

    review_parser = subparsers.add_parser("review-event", help="Send a review workflow event")
    review_parser.add_argument(
        "--event",
        required=True,
        choices=[
            "review_returned_for_revision",
            "review_ready_for_human_confirmation",
            "human_confirmed",
            "human_rejected",
            "final_review_passed",
            "final_review_rejected",
        ],
        help="Review workflow event name",
    )
    review_parser.add_argument("--summary", required=True, help="Review summary for Coordinator/Bitable")
    review_parser.add_argument("--review-notes-url", default="", help="Optional review notes URL")
    review_parser.add_argument("--document-url", default="", help="Optional current requirement document URL")
    review_parser.add_argument("--review-result", default="", help="Optional external review result label")

    subparsers.add_parser("fetch-context", help="Query requirement context for an agent by req_id")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.mode:
        parser.error("a callback mode is required")

    base_url = args.base_url.rstrip("/")
    if args.mode == "author-ready":
        endpoint = AUTHOR_ENDPOINT
        payload = build_author_payload(args)
    elif args.mode == "fetch-context":
        endpoint = CONTEXT_QUERY_ENDPOINT
        payload = build_context_query_payload(args)
    else:
        endpoint = REVIEW_ENDPOINT
        payload = build_review_payload(args)

    return post_json(f"{base_url}{endpoint}", payload, args.secret or None)


if __name__ == "__main__":
    raise SystemExit(main())
