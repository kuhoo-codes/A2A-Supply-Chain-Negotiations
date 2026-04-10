from uuid import uuid4

from backend.app.core.config import Settings


class LangfuseTraceWrapper:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_status(self) -> tuple[bool, bool, str]:
        if not self.settings.langfuse_enabled:
            return False, False, "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are not configured."

        try:
            import langfuse  # noqa: F401
        except ImportError:
            return True, False, "Langfuse package is not installed."

        return True, True, "Configured for tracing."

    def create_trace_reference(self, run_id: str) -> str | None:
        configured, available, _ = self.get_status()
        if not configured or not available:
            return None

        return f"trace-{run_id}-{uuid4().hex[:8]}"
