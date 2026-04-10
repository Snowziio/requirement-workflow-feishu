from __future__ import annotations

import logging
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent
SRC_ROOT = APP_ROOT / "src"
if not SRC_ROOT.exists():
    candidate = APP_ROOT.parent / "src"
    if candidate.exists():
        SRC_ROOT = candidate

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from requirement_workflow_v12.service_app import create_runtime_app


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


if __name__ == "__main__":
    create_runtime_app().start()
