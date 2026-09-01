"""
Async‑safe logging with QueueHandler + QueueListener.
Provides simple functions: info, warning, error, debug, exception.
"""

import logging
import sys
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from queue import Queue
from typing import Optional

# ─── Module‑level logger (always exists, never None) ──────
_logger = logging.getLogger("app")
_listener: Optional[QueueListener] = None
_initialised = False


def setup_logging(
        level: int = logging.INFO,
        log_file: str = "app.log",
        max_bytes: int = 5_000_000,
        backup_count: int = 3,
        console: bool = True,
) -> None:
    """
    Configure the logging system. Must be called once at startup.
    """
    global _logger, _listener, _initialised

    if _initialised:
        return

    # ─── Root logger ──────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # ─── Handlers that actually write logs ──────────────────
    handlers = []

    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count
    )
    file_handler.setFormatter(formatter)
    handlers.append(file_handler)

    # ─── QueueHandler (async‑safe) ───────────────────────────
    queue = Queue(-1)
    queue_handler = QueueHandler(queue)
    root.addHandler(queue_handler)

    # ─── QueueListener (runs in background thread) ───────────
    listener = QueueListener(queue, *handlers)
    listener.start()
    _listener = listener

    # ─── Configure our module logger ────────────────────────
    _logger.setLevel(level)
    _logger.handlers.clear()
    _logger.addHandler(queue_handler)
    _logger.propagate = False

    # ─── Suppress noisy third‑party loggers ──────────────────
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)

    _initialised = True
    _logger.info("Logging system initialised (async‑safe QueueHandler)")


def shutdown_logging() -> None:
    """Stop the QueueListener and flush remaining logs."""
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None


# ─── Convenience logging functions (always safe) ───────────

def debug(msg: str, *args, **kwargs) -> None:
    _logger.debug(msg, *args, **kwargs)


def info(msg: str, *args, **kwargs) -> None:
    _logger.info(msg, *args, **kwargs)


def warning(msg: str, *args, **kwargs) -> None:
    _logger.warning(msg, *args, **kwargs)


def error(msg: str, *args, **kwargs) -> None:
    _logger.error(msg, *args, **kwargs)


def exception(msg: str, *args, **kwargs) -> None:
    """Log an error with full traceback (use inside except block)."""
    _logger.exception(msg, *args, **kwargs)


def critical(msg: str, *args, **kwargs) -> None:
    _logger.critical(msg, *args, **kwargs)
