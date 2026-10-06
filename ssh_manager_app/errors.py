"""Bounded diagnostics without exception messages, locals or source lines."""
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
import traceback

from .constants import _APPDATA_DIR


def record_failure(error: BaseException) -> None:
    try:
        logger = logging.getLogger("ssh_manager.errors")
        if not logger.handlers:
            _APPDATA_DIR.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(_APPDATA_DIR / "error.log", maxBytes=262144, backupCount=3, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            logger.addHandler(handler)
            logger.propagate = False
        frames = traceback.extract_tb(error.__traceback__)
        # No repr(error), source text or paths: these can contain credentials.
        location = " > ".join(f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}" for frame in frames)
        logger.error("%s %s", type(error).__name__, location)
    except (OSError, ValueError):
        # A broken log destination must not hide the visible error message.
        pass
