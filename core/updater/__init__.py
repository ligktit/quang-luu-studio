"""core.updater — cập nhật ngầm qua Velopack (xem velopack_updater.py)."""
from core.updater.velopack_updater import (  # noqa: F401
    apply_pending_on_exit,
    get_updater,
    start_background_updates,
    status_text,
)

__all__ = ["start_background_updates", "get_updater", "apply_pending_on_exit", "status_text"]
