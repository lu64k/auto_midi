"""Environment-backed application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean, got {value!r}")


def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if not value or not value.strip():
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    bpm: int = _env_int("AUTO_MIDI_BPM", 92)
    complexity: int = _env_int("AUTO_MIDI_COMPLEXITY", 55)
    intensity: int = _env_int("AUTO_MIDI_INTENSITY", 65)
    fill: int = _env_int("AUTO_MIDI_FILL", 35)
    randomness: int = _env_int("AUTO_MIDI_RANDOMNESS", 45)
    preset: str = os.getenv("AUTO_MIDI_PRESET", "free")
    groove: str = os.getenv("AUTO_MIDI_GROOVE", "")
    time_signature: str = os.getenv("AUTO_MIDI_TIME_SIGNATURE", "4/4")
    sample_kit: Path = _env_path("AUTO_MIDI_SAMPLE_KIT", PROJECT_ROOT / "samples" / "classic_kit")
    output_dir: Path = _env_path("AUTO_MIDI_OUTPUT_DIR", PROJECT_ROOT / "outputs")
    gradio_server_name: str = os.getenv("GRADIO_SERVER_NAME", "0.0.0.0")
    gradio_server_port: int = _env_int("GRADIO_SERVER_PORT", 8006)
    gradio_share: bool = _env_bool("GRADIO_SHARE", False)
    test_mode: bool = _env_bool("AUTO_MIDI_TEST_MODE", True)


settings = Settings()
