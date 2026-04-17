"""List all chats the bot belongs to. Prints chat_id + name."""
from __future__ import annotations

import os
import sys

import lark_oapi as lark
from lark_oapi.api.im.v1 import ListChatRequest


def main() -> None:
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        print("ERROR: set FEISHU_APP_ID and FEISHU_APP_SECRET", file=sys.stderr)
        sys.exit(1)

    client = (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .build()
    )

    page_token = ""
    while True:
        req_builder = ListChatRequest.builder().page_size(50)
        if page_token:
            req_builder = req_builder.page_token(page_token)
        request = req_builder.build()
        response = client.im.v1.chat.list(request)

        if not response.success():
            print(f"API error: code={response.code} msg={response.msg}", file=sys.stderr)
            sys.exit(1)

        items = response.data.items or []
        for chat in items:
            print(f"  chat_id: {chat.chat_id}")
            print(f"  name:    {chat.name}")
            print(f"  owner:   {chat.owner_id_type}:{chat.owner_id}")
            print()

        if not response.data.has_more:
            break
        page_token = response.data.page_token

    if not items:
        print("(no chats found — is the bot added to any group?)")


if __name__ == "__main__":
    main()
