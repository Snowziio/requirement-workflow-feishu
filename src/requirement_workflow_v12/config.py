from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    service_name: str = os.environ.get("SERVICE_NAME", "coordinator-service")
    service_port: int = int(os.environ.get("SERVICE_PORT", "8003"))
    feishu_app_id: str = os.environ.get("FEISHU_APP_ID", "")
    feishu_app_secret: str = os.environ.get("FEISHU_APP_SECRET", "")
    feishu_user_access_token: str = os.environ.get("FEISHU_USER_ACCESS_TOKEN", "")
    feishu_verification_token: str = os.environ.get("FEISHU_VERIFICATION_TOKEN", "")
    feishu_encrypt_key: str = os.environ.get("FEISHU_ENCRYPT_KEY", "")
    feishu_log_level: str = os.environ.get("FEISHU_LOG_LEVEL", "INFO")
    feishu_bitable_app_token: str = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "")
    feishu_bitable_table_id: str = os.environ.get("FEISHU_BITABLE_TABLE_ID", "")
    feishu_doc_folder_token: str = os.environ.get("FEISHU_DOC_FOLDER_TOKEN", "")
    feishu_base_url: str = os.environ.get("FEISHU_BASE_URL", "https://my.feishu.cn")
    feishu_user_id_type: str = os.environ.get("FEISHU_USER_ID_TYPE", "open_id")
    creation_group_chat_id: str = os.environ.get("FEISHU_CREATION_GROUP_CHAT_ID", "")
    project_group_name_template: str = os.environ.get("PROJECT_GROUP_NAME_TEMPLATE", "{project} 需求群")
    requirement_template_url: str = os.environ.get("REQUIREMENT_TEMPLATE_URL", "")
    ui_template_url: str = os.environ.get("UI_TEMPLATE_URL", "")
    review_template_url: str = os.environ.get("REVIEW_TEMPLATE_URL", "")
    openclaw_author_agent_name: str = os.environ.get("OPENCLAW_AUTHOR_AGENT_NAME", "需求构造助手")
    openclaw_reviewer_agent_name: str = os.environ.get("OPENCLAW_REVIEWER_AGENT_NAME", "需求审查助手")
    state_store_path: str = os.environ.get("STATE_STORE_PATH", "state/coordinator_state.json")

    def validate_runtime(self) -> None:
        missing = []
        if not self.feishu_app_id:
            missing.append("FEISHU_APP_ID")
        if not self.feishu_app_secret:
            missing.append("FEISHU_APP_SECRET")
        if missing:
            raise ValueError(f"Missing required settings: {', '.join(missing)}")


def load_settings() -> Settings:
    return Settings()
