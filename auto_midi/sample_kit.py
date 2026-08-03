from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil


REQUIRED_VOICES = (
    "kick",
    "snare",
    "closed_hat",
    "open_hat",
    "low_tom",
    "mid_tom",
    "crash",
)

OPTIONAL_FALLBACKS = {
    "rim": "snare",
    "clap": "snare",
    "ride": "crash",
}

VOICE_HINTS = {
    "kick": ("kick", "bass drum", "bassdrum", "bd"),
    "snare": ("snare", "snr", "sd"),
    "rim": ("rim", "sidestick", "side stick"),
    "clap": ("clap",),
    "closed_hat": ("closed hat", "closed_hat", "closed-hat", "chh", "hat closed", "hihat closed", "hi hat closed", "hi hat"),
    "open_hat": ("open hat", "open_hat", "open-hat", "ohh", "hat open", "hihat open", "hi hat open"),
    "low_tom": ("low tom", "low_tom", "floor tom", "floor_tom", "tom floor", "tom low", "tom3"),
    "mid_tom": ("mid tom", "mid_tom", "rack tom", "tom mid", "tom2", "tom1"),
    "crash": ("crash",),
    "ride": ("ride",),
}


@dataclass(frozen=True)
class KitStatus:
    kit_dir: Path
    samples: dict[str, Path]
    missing: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.missing


def inspect_kit(kit_dir: Path) -> KitStatus:
    samples: dict[str, Path] = {}
    for voice in set(REQUIRED_VOICES) | set(OPTIONAL_FALLBACKS):
        path = kit_dir / f"{voice}.wav"
        if path.exists():
            samples[voice] = path

    for voice, fallback in OPTIONAL_FALLBACKS.items():
        if voice not in samples and fallback in samples:
            samples[voice] = samples[fallback]

    missing = tuple(voice for voice in REQUIRED_VOICES if voice not in samples)
    return KitStatus(kit_dir=kit_dir, samples=samples, missing=missing)


def prepare_kit(source: Path, target: Path) -> KitStatus:
    files = sorted(path for path in source.rglob("*.wav") if path.is_file())
    if not files:
        raise ValueError(f"no .wav files found under {source}")

    target.mkdir(parents=True, exist_ok=True)
    selected: dict[str, Path] = {}
    for voice in REQUIRED_VOICES + tuple(OPTIONAL_FALLBACKS):
        match = _best_match(files, voice)
        if match is not None:
            selected[voice] = match
            shutil.copyfile(match, target / f"{voice}.wav")

    return inspect_kit(target)


def _best_match(files: list[Path], voice: str) -> Path | None:
    hints = VOICE_HINTS.get(voice, (voice,))
    scored: list[tuple[int, int, Path]] = []
    for path in files:
        name = _normalize(path.stem)
        full = _normalize(str(path))
        score = 0
        for hint in hints:
            normalized_hint = _normalize(hint)
            if normalized_hint in name:
                score += 8
            elif normalized_hint in full:
                score += 3
        if "soft" in name or "quiet" in name:
            score -= 2
        if "hard" in name or "loud" in name:
            score += 1
        if score > 0:
            scored.append((score, -len(path.name), path))
    if not scored:
        return None
    return max(scored)[2]


def _normalize(value: str) -> str:
    return value.lower().replace("_", " ").replace("-", " ")
