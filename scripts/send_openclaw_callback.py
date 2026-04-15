#!/usr/bin/env python3

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


AUTHOR_ENDPOINT = "/callbacks/openclaw/author-turn"
REVIEW_ENDPOINT = "/callbacks/openclaw/review-result"
CONTEXT_QUERY_ENDPOINT = "/queries/openclaw/requirement-context"
SPEC_CONTEXT_QUERY_ENDPOINT = "/queries/openclaw/spec-context"
SPEC_TURN_ENDPOINT = "/callbacks/openclaw/spec-turn"
DEFAULT_COORDINATOR_BASE_URL = "http://127.0.0.1:8004"


def build_signature(secret: str, timestamp: str, raw_body: bytes) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()


def build_author_payload(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "req_id": args.req_id,
        "event": "author_submit",
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


def build_spec_start_payload(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "req_id": args.req_id,
        "event": "spec_start",
        "summary": args.summary,
    }


def build_spec_submit_payload(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "req_id": args.req_id,
        "event": "spec_submit",
        "summary": args.summary,
        "spec_document_url": args.spec_document_url or "",
        "context_token": args.context_token or "",
        "architecture_doc_revision": args.architecture_doc_revision or "",
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
    parser.add_argument(
        "--base-url",
        default="",
        help="Coordinator base URL. Defaults to $COORDINATOR_BASE_URL or http://127.0.0.1:8004",
    )
    parser.add_argument("--secret", default="", help="Optional callback signing secret. Defaults to $OPENCLAW_CALLBACK_SECRET")
    parser.add_argument("--req-id", required=True, help="Requirement ID, e.g. REQ-HARNESS-001")

    subparsers = parser.add_subparsers(dest="mode")

    author_parser = subparsers.add_parser("author-ready", help="Send author_submit")
    author_parser.add_argument("--summary", required=True, help="Event summary for Coordinator/Bitable")
    author_parser.add_argument("--document-url", default="", help="Current requirement document URL")
    author_parser.add_argument("--document-version", default="", help="Optional document version label")
    author_parser.add_argument("--iteration-round", type=int, default=None, help="Optional document iteration round")

    review_parser = subparsers.add_parser("review-event", help="Send a review workflow event")
    review_parser.add_argument(
        "--event",
        required=True,
        choices=[
            "ai_review_reject",
            "ai_review_pass",
        ],
        help="Review workflow event name",
    )
    review_parser.add_argument("--summary", required=True, help="Review summary for Coordinator/Bitable")
    review_parser.add_argument("--review-notes-url", default="", help="Optional review notes URL")
    review_parser.add_argument("--document-url", default="", help="Optional current requirement document URL")
    review_parser.add_argument("--review-result", default="", help="Optional external review result label")

    subparsers.add_parser("fetch-context", help="Query requirement context for an agent by req_id")
    subparsers.add_parser("spec-context", help="Query spec-layer context (architecture_doc_url, revision, context_token) for Spec Agent by req_id")

    spec_start_parser = subparsers.add_parser("spec-start", help="Notify Coordinator that Spec Agent has started drafting")
    spec_start_parser.add_argument("--summary", required=True, help="Brief summary for Coordinator logs")

    spec_submit_parser = subparsers.add_parser("spec-submit", help="Notify Coordinator that Spec Agent has submitted a draft for review")
    spec_submit_parser.add_argument("--summary", required=True, help="Spec draft completion summary")
    spec_submit_parser.add_argument("--spec-document-url", default="", help="URL of the completed spec document")
    spec_submit_parser.add_argument("--context-token", default="", help="Spec context token returned by fetch-context")
    spec_submit_parser.add_argument("--architecture-doc-revision", default="", help="ARCHITECTURE Feishu doc revision at submit time")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.mode:
        parser.error("a callback mode is required")

    base_url = (args.base_url or os.environ.get("COORDINATOR_BASE_URL") or DEFAULT_COORDINATOR_BASE_URL).rstrip("/")
    secret = args.secret or os.environ.get("OPENCLAW_CALLBACK_SECRET") or None
    if args.mode == "author-ready":
        endpoint = AUTHOR_ENDPOINT
        payload = build_author_payload(args)
    elif args.mode == "fetch-context":
        endpoint = CONTEXT_QUERY_ENDPOINT
        payload = build_context_query_payload(args)
    elif args.mode == "spec-context":
        endpoint = SPEC_CONTEXT_QUERY_ENDPOINT
        payload = build_context_query_payload(args)
    elif args.mode in ("spec-start", "spec-submit"):
        endpoint = SPEC_TURN_ENDPOINT
        if args.mode == "spec-start":
            payload = build_spec_start_payload(args)
        else:
            payload = build_spec_submit_payload(args)
    else:
        endpoint = REVIEW_ENDPOINT
        payload = build_review_payload(args)

    return post_json(f"{base_url}{endpoint}", payload, secret)


if __name__ == "__main__":
    raise SystemExit(main())
