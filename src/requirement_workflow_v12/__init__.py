from .compiler import RequirementDocumentCompiler
from .coordinator_service import AuthorTurnResult, CoordinatorService
from .config import Settings, load_settings
from .models import DISCUSSION_FIELDS, Requirement, RequirementDocument, ReviewFinding, ReviewResult, WorkflowStatus
from .protocols import AuthorStartBinding, AuthorStartResponse, CreationRequest, CreationResponse
from .store import JsonStateStore
from .state_machine import Event, TransitionDecision, apply_event

try:
    from .service_app import CoordinatorRuntimeApp, create_runtime_app
except Exception:  # pragma: no cover - allow core imports before runtime deps are installed
    CoordinatorRuntimeApp = None
    create_runtime_app = None

__all__ = [
    "AuthorTurnResult",
    "AuthorStartBinding",
    "AuthorStartResponse",
    "CoordinatorService",
    "CreationRequest",
    "CreationResponse",
    "DISCUSSION_FIELDS",
    "Event",
    "JsonStateStore",
    "Requirement",
    "RequirementDocument",
    "RequirementDocumentCompiler",
    "ReviewFinding",
    "ReviewResult",
    "Settings",
    "TransitionDecision",
    "WorkflowStatus",
    "apply_event",
    "load_settings",
]

if CoordinatorRuntimeApp is not None:
    __all__.append("CoordinatorRuntimeApp")
if create_runtime_app is not None:
    __all__.append("create_runtime_app")
