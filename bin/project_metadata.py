#!/usr/bin/env python3
"""Helpers for sansheng-liubu runtime metadata stored outside openclaw.json."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


METADATA_FILENAME = "sansheng-liubu.json"
LEGACY_CONFIG_KEY = "sanshengLiubu"


def metadata_path(openclaw_dir):
    return Path(openclaw_dir).expanduser().resolve() / METADATA_FILENAME


def _load_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def extract_legacy_metadata(config):
    metadata = config.get(LEGACY_CONFIG_KEY, {}) if isinstance(config, dict) else {}
    return deepcopy(metadata) if isinstance(metadata, dict) else {}


def load_project_metadata(openclaw_dir, existing_config=None):
    sidecar = _load_json(metadata_path(openclaw_dir))
    config = existing_config
    if config is None:
        config_path = Path(openclaw_dir).expanduser().resolve() / "openclaw.json"
        config = _load_json(config_path)
    legacy = extract_legacy_metadata(config)
    if isinstance(sidecar, dict) and sidecar:
        return {**legacy, **sidecar}

    return legacy


def sanitize_openclaw_config(config):
    clean = deepcopy(config)
    if isinstance(clean, dict):
        clean.pop(LEGACY_CONFIG_KEY, None)
    return clean


def write_project_metadata(openclaw_dir, metadata):
    path = metadata_path(openclaw_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        key: value
        for key, value in deepcopy(metadata).items()
        if value not in (None, "")
    }
    payload["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
