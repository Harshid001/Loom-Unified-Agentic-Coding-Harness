from loom.orchestrator.state import NodeStatus, OrchestratorState
from loom.orchestrator.task_graph import RunStatus, TaskGraph

# Apply terminal-state/webhook normalization for direct TaskGraph callers as
# well as the fully composed FastAPI application. The installer is idempotent.
from loom.api.late_hardening import install_terminal_webhook_normalizer
install_terminal_webhook_normalizer()

__all__ = [
    "OrchestratorState",
    "NodeStatus",
    "TaskGraph",
    "RunStatus",
]
