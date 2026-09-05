"""Loads the runtime-editable YAML config (config/*.yaml).

Nothing here is cached beyond process lifetime on purpose: config changes
(new category, new city, new cadence) should take effect on the next
process restart / scheduler tick without a code deploy.
"""
from functools import lru_cache
from pathlib import Path
import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_yaml(filename: str) -> dict:
    path = CONFIG_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=None)
def get_locations() -> dict:
    return _load_yaml("locations.yaml")


@lru_cache(maxsize=None)
def get_categories() -> dict:
    return _load_yaml("categories.yaml")["categories"]


@lru_cache(maxsize=None)
def get_templates() -> dict:
    return _load_yaml("templates.yaml")


@lru_cache(maxsize=None)
def get_media_library() -> dict:
    return _load_yaml("media_library.yaml")


@lru_cache(maxsize=None)
def get_follow_up_policy() -> dict:
    return _load_yaml("follow_up_policy.yaml")


def clear_config_cache() -> None:
    """Call after editing YAML in-process (e.g. in tests) to force a reload."""
    get_locations.cache_clear()
    get_categories.cache_clear()
    get_templates.cache_clear()
    get_media_library.cache_clear()
    get_follow_up_policy.cache_clear()
