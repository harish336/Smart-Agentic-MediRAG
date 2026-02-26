"""
Smart Medirag — YAML Configuration Loader

Loads:
- db.yaml
- models.yaml
- prompts.yaml
- settings.yaml

Usage:
    from config.system_loader import get_database_config
"""

import os
import yaml

# -------------------------------------------------
# Base Config Path
# -------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_yaml(filename: str):
    path = os.path.join(BASE_DIR, filename)

    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# -------------------------------------------------
# Public Config Getters
# -------------------------------------------------

def get_database_config():
    return _load_yaml("db.yaml")


def get_model_config():
    return _load_yaml("models.yaml")


def get_prompt_config():
    return _load_yaml("prompts.yaml")


def get_system_config():
    return _load_yaml("settings.yaml")