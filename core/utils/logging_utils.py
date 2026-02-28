import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

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


def get_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
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

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    log_path = _resolve_log_path(log_file)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        logger.exception("Failed to initialize file logging at %s", log_path)

    logger._smartchunk_configured = True
    return logger


def get_component_logger(
    name: str,
    component: Optional[str] = None,
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    resolved_path = _resolve_component_log_path(component, log_file)
    return get_logger(name, level=level, log_file=str(resolved_path))
