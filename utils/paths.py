from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


def get_base_dir() -> Path:
    return BASE_DIR


def get_config_path() -> Path:
    return BASE_DIR / "config.yaml"


def get_logs_dir() -> Path:
    path = BASE_DIR / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_memory_root() -> Path:
    path = BASE_DIR / "memory"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_models_dir() -> Path:
    path = BASE_DIR / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_chats_dir() -> Path:
    path = BASE_DIR / "chats"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_codes_dir() -> Path:
    path = BASE_DIR / "codes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_images_generated_dir() -> Path:
    path = BASE_DIR / "images" / "generated"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_images_uploaded_dir() -> Path:
    path = BASE_DIR / "images" / "uploaded"
    path.mkdir(parents=True, exist_ok=True)
    return path
