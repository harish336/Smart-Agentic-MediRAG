import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener
from pathlib import Path
from typing import Optional
from queue import Queue


# =====================================================
# WINDOWS-SAFE ROTATING FILE HANDLER
# =====================================================

class WindowsSafeRotatingFileHandler(RotatingFileHandler):
    """
    Custom RotatingFileHandler that handles Windows file locking gracefully.
    On Windows, file rotation can fail if the file is being accessed by another process.
    This handler catches and suppresses those errors.
    """

    _last_lock_warning_ts = 0.0
    _LOCK_WARNING_INTERVAL_SECONDS = 60.0

    @staticmethod
    def _is_windows_lock_error(exc: Exception) -> bool:
        text = str(exc)
        return "WinError 32" in text or "The process cannot access the file" in text

    @classmethod
    def _warn_lock_once(cls, message: str):
        """
        Throttle repetitive Windows lock warnings so transient lock contention
        does not flood stderr.
        """
        now = time.time()
        if (now - cls._last_lock_warning_ts) >= cls._LOCK_WARNING_INTERVAL_SECONDS:
            sys.stderr.write(message)
            cls._last_lock_warning_ts = now

    def emit(self, record):
        """
        Override emit to suppress noisy traceback from logging internals when
        rollover hits a transient Windows lock.
        """
        try:
            super().emit(record)
        except (OSError, PermissionError) as e:
            if self._is_windows_lock_error(e):
                self._warn_lock_once(
                    f"[WARNING] Log write skipped due to Windows file lock: {e}\n"
                )
                return
            raise

    def doRollover(self):
        """Override doRollover to handle Windows file locking errors."""
        try:
            super().doRollover()
        except (OSError, PermissionError) as e:
            # On Windows, file might be locked by another process during rotation
            # Log to console but don't fail
            if self._is_windows_lock_error(e):
                # Retry a few times with delays
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        time.sleep(0.1)  # Wait 100ms before retry
                        super().doRollover()
                        return
                    except (OSError, PermissionError):
                        if attempt == max_retries - 1:
                            # Give up but don't crash
                            self._warn_lock_once(
                                f"[WARNING] Log rotation failed (Windows file lock): {e}\n"
                            )
                            return
            else:
                # For other OS errors, still fail gracefully
                sys.stderr.write(f"[WARNING] Log rotation failed: {e}\n")


_DEFAULT_LOG_NAME = "smartchunk.log"
_DEFAULT_LOG_DIR = Path(os.getenv("SMARTCHUNK_LOG_DIR", "logs"))
_DEFAULT_LOG_FILE = os.getenv("SMARTCHUNK_LOG_FILE")

_COMPONENT_LOG_FILES = {
    "ingestion": "ingestion.log",
    "retrieval": "retrieval.log",
    "answering": "answering.log"
}
_COMPONENT_ENV_FILES = {
    "ingestion": "SMARTCHUNK_INGESTION_LOG_FILE",
    "retrieval": "SMARTCHUNK_RETRIEVAL_LOG_FILE",
    "answering": "SMARTCHUNK_ANSWERING_LOG_FILE"
}

# Global queue and listener for thread-safe logging
_LOG_QUEUE: Optional[Queue] = None
_LOG_LISTENER: Optional[QueueListener] = None
_QUEUE_HANDLERS = {}


def _resolve_log_path(log_file: Optional[str]) -> Path:
    if log_file:
        return Path(log_file)
    if _DEFAULT_LOG_FILE:
        return Path(_DEFAULT_LOG_FILE)
    return _DEFAULT_LOG_DIR / _DEFAULT_LOG_NAME


def _resolve_component_log_path(
    component: Optional[str],
    log_file: Optional[str]
) -> Path:
    if log_file:
        return Path(log_file)

    if component:
        env_key = _COMPONENT_ENV_FILES.get(component)
        if env_key:
            env_path = os.getenv(env_key)
            if env_path:
                return Path(env_path)

        component_file = _COMPONENT_LOG_FILES.get(component)
        if component_file:
            return _DEFAULT_LOG_DIR / component_file

    return _resolve_log_path(log_file)


def _init_queue_listener() -> Queue:
    """Initialize the global queue and listener for thread-safe logging."""
    global _LOG_QUEUE, _LOG_LISTENER
    
    if _LOG_QUEUE is not None:
        return _LOG_QUEUE
    
    _LOG_QUEUE = Queue()
    
    # Create handlers for the listener
    handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    ))
    handlers.append(console_handler)
    
    # Start the listener
    _LOG_LISTENER = QueueListener(_LOG_QUEUE, *handlers, respect_handler_level=True)
    _LOG_LISTENER.start()
    
    return _LOG_QUEUE


def get_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """Get or create a logger with file and console handlers."""
    logger = logging.getLogger(name)

    if getattr(logger, "_smartchunk_configured", False):
        if level is not None:
            logger.setLevel(level)
        return logger

    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    )

    # Console handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # File handler with Windows-safe file rotation
    log_path = _resolve_log_path(log_file)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Use Windows-safe rotating file handler
        file_handler = WindowsSafeRotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=5,
            encoding="utf-8",
            delay=True  # Delay file creation until first write
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.exception("Failed to initialize file logging at %s: %s", log_path, e)

    logger._smartchunk_configured = True
    return logger


def get_component_logger(
    name: str,
    component: Optional[str] = None,
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """Get a component-specific logger with proper file handling."""
    resolved_path = _resolve_component_log_path(component, log_file)
    return get_logger(name, level=level, log_file=str(resolved_path))


def shutdown_logging():
    """Shutdown the logging queue listener gracefully."""
    global _LOG_LISTENER
    if _LOG_LISTENER is not None:
        _LOG_LISTENER.stop()
        _LOG_LISTENER = None
