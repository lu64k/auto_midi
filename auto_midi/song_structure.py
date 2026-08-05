"""User-authored song structure and section-level chord context.

This module deliberately contains no LLM logic.  The song form, bar counts,
and chord changes are authored by the user; later agents may consume this
validated structure but must not silently replace it.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping


SECTION_TYPES = (
    "intro",
    "verse",
    "pre_chorus",
    "chorus",
    "bridge",
    "instrumental",
    "outro",
)


@dataclass(frozen=True)
class SongSection:
    id: str
    type: str
    bars: int
    lyrics_start: int | None = None
    lyrics_end: int | None = None
    chord_bars: tuple[tuple[str, ...], ...] = ()
    index: int | None = None
    repeat_of: str | None = None

    @property
    def has_chords(self) -> bool:
        return bool(self.chord_bars)


@dataclass(frozen=True)
class SongStructure:
    title: str
    bpm: int
    time_signature: str
    key: str | None
    sections: tuple[SongSection, ...]

    @property
    def total_bars(self) -> int:
        return sum(section.bars for section in self.sections)


def load_song_structure(path: Path) -> SongStructure:
    """Load and validate a user-authored structure JSON file."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"song structure JSON cannot be read: {exc}") from exc
    return parse_song_structure(payload)


def parse_song_structure(payload: Mapping[str, Any]) -> SongStructure:
    """Parse a structure object without inferring missing musical content."""

    if not isinstance(payload, Mapping):
        raise ValueError("song structure must be a JSON object")
    raw_sections = payload.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise ValueError("song structure must contain a non-empty sections list")

    try:
        bpm = int(payload.get("bpm", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("song structure bpm must be an integer") from exc
    if not 30 <= bpm <= 260:
        raise ValueError("song structure bpm must be between 30 and 260")

    time_signature = str(payload.get("time_signature", "")).strip()
    if not time_signature:
        raise ValueError("song structure time_signature is required")

    sections: list[SongSection] = []
    ids: set[str] = set()
    for position, raw in enumerate(raw_sections):
        sections.append(_parse_section(raw, position, ids))

    section_ids = {section.id for section in sections}
    for section in sections:
        if section.repeat_of is not None:
            if section.repeat_of not in section_ids:
                raise ValueError(
                    f"section {section.id} repeat_of references unknown section {section.repeat_of!r}"
                )
            if section.repeat_of == section.id:
                raise ValueError(f"section {section.id} cannot repeat itself")

    return SongStructure(
        title=str(payload.get("title", "untitled")).strip() or "untitled",
        bpm=bpm,
        time_signature=time_signature,
        key=_optional_text(payload.get("key")),
        sections=tuple(sections),
    )


def validate_against_lyrics(structure: SongStructure, lyric_line_count: int) -> None:
    """Ensure authored section bar counts cover the lyric bars exactly."""

    if lyric_line_count <= 0:
        raise ValueError("lyrics must contain at least one non-empty line")
    if structure.total_bars != lyric_line_count:
        raise ValueError(
            f"song structure contains {structure.total_bars} bars, "
            f"but lyrics contain {lyric_line_count} non-empty lines"
        )

    cursor = 1
    for section in structure.sections:
        expected_start = cursor
        expected_end = cursor + section.bars - 1
        if section.lyrics_start is not None and section.lyrics_start != expected_start:
            raise ValueError(
                f"section {section.id} lyrics_start must be {expected_start}, "
                f"got {section.lyrics_start}"
            )
        if section.lyrics_end is not None and section.lyrics_end != expected_end:
            raise ValueError(
                f"section {section.id} lyrics_end must be {expected_end}, "
                f"got {section.lyrics_end}"
            )
        cursor = expected_end + 1


def apply_song_structure(text_map, structure: SongStructure):
    """Apply authored section boundaries to a parsed lyric map.

    The user structure is authoritative here, so lyric input does not need
    blank lines between sections.  Existing token, phrase, and rhyme analysis
    is preserved while only section indices and section-end markers change.
    """

    validate_against_lyrics(structure, len(text_map.bars))
    from .text_parser import BarText, TextMap

    section_by_bar: list[int] = []
    for section_index, section in enumerate(structure.sections):
        section_by_bar.extend([section_index] * section.bars)

    bars = []
    for index, bar in enumerate(text_map.bars):
        section_index = section_by_bar[index]
        ends_section = index == len(text_map.bars) - 1 or section_by_bar[index + 1] != section_index
        bars.append(
            BarText(
                index=bar.index,
                section=section_index,
                text=bar.text,
                tokens=bar.tokens,
                token_units=bar.token_units,
                phrases=bar.phrases,
                punctuation_positions=bar.punctuation_positions,
                rhyme_key=bar.rhyme_key,
                ends_section=ends_section,
            )
        )
    return TextMap(bars=tuple(bars), section_count=len(structure.sections))


def section_configs_from_song_structure(structure: SongStructure, text_map) -> tuple:
    """Convert user-authored structure into the existing execution sections.

    The import is intentionally local so the structure model stays independent
    from the drum execution layer.  Chords are carried as context for the
    upcoming agents; the current drum generator simply ignores them.
    """

    validate_against_lyrics(structure, len(text_map.bars))

    from .section_config import SectionConfig

    result = []
    for section in structure.sections:
        result.append(
            SectionConfig(
                name=section.id,
                bars=section.bars,
                section_type=section.type,
                chord_bars=resolved_chord_bars(structure, section.id),
                repeat_of=section.repeat_of,
            )
        )
    return tuple(result)


def resolved_chord_bars(structure: SongStructure, section_id: str) -> tuple[tuple[str, ...], ...]:
    """Return only explicitly authored chords, resolving explicit section reuse.

    An empty chord list means "no chord context".  It is never treated as a
    request to invent or randomly carry chords through the song.
    """

    sections = {section.id: section for section in structure.sections}
    if section_id not in sections:
        raise ValueError(f"unknown section {section_id!r}")

    visited: set[str] = set()
    current = sections[section_id]
    while current.repeat_of is not None and not current.chord_bars:
        if current.id in visited:
            raise ValueError(f"cyclic repeat_of reference at section {current.id}")
        visited.add(current.id)
        current = sections[current.repeat_of]
    return current.chord_bars


def _parse_section(raw: Any, position: int, ids: set[str]) -> SongSection:
    if not isinstance(raw, Mapping):
        raise ValueError(f"section {position} must be an object")

    section_id = _required_text(raw.get("id"), f"section {position} id")
    if section_id in ids:
        raise ValueError(f"duplicate section id {section_id!r}")
    ids.add(section_id)

    section_type = _required_text(raw.get("type"), f"section {section_id} type").lower()
    if section_type not in SECTION_TYPES:
        raise ValueError(
            f"section {section_id} type must be one of {SECTION_TYPES}, got {section_type!r}"
        )
    try:
        bars = int(raw.get("bars"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"section {section_id} bars must be an integer") from exc
    if bars <= 0:
        raise ValueError(f"section {section_id} bars must be positive")

    lyrics_start = _optional_positive_int(raw.get("lyrics_start"), f"section {section_id} lyrics_start")
    lyrics_end = _optional_positive_int(raw.get("lyrics_end"), f"section {section_id} lyrics_end")
    if lyrics_start is not None and lyrics_end is not None and lyrics_end - lyrics_start + 1 != bars:
        raise ValueError(f"section {section_id} lyrics range must contain exactly {bars} lines")

    chord_value = raw.get("chord_bars", raw.get("chords", []))
    chord_bars = _parse_chord_bars(chord_value, section_id, bars)
    repeat_of = _optional_text(raw.get("repeat_of"))

    index = raw.get("index")
    if index is not None:
        try:
            index = int(index)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"section {section_id} index must be an integer") from exc
        if index <= 0:
            raise ValueError(f"section {section_id} index must be positive")

    return SongSection(
        id=section_id,
        type=section_type,
        bars=bars,
        lyrics_start=lyrics_start,
        lyrics_end=lyrics_end,
        chord_bars=chord_bars,
        index=index,
        repeat_of=repeat_of,
    )


def _parse_chord_bars(value: Any, section_id: str, bars: int) -> tuple[tuple[str, ...], ...]:
    if value in (None, []):
        return ()
    if not isinstance(value, list):
        raise ValueError(f"section {section_id} chords must be a list")

    # Accept a flat list as a convenience: ["E", "B"] means one chord per bar.
    if all(isinstance(item, str) for item in value):
        normalized = tuple((_required_text(item, f"section {section_id} chord"),) for item in value)
    else:
        normalized_items: list[tuple[str, ...]] = []
        for bar_index, bar_chords in enumerate(value, start=1):
            if isinstance(bar_chords, str):
                bar_chords = [bar_chords]
            if not isinstance(bar_chords, list) or not bar_chords:
                raise ValueError(f"section {section_id} chord bar {bar_index} must be a non-empty list")
            if not all(isinstance(chord, str) and chord.strip() for chord in bar_chords):
                raise ValueError(f"section {section_id} chord bar {bar_index} contains an invalid chord")
            normalized_items.append(tuple(chord.strip() for chord in bar_chords))
        normalized = tuple(normalized_items)

    if len(normalized) != bars:
        raise ValueError(
            f"section {section_id} provides {len(normalized)} chord bars, expected {bars}; "
            "use [] when this section has no chord context"
        )
    return normalized


def _required_text(value: Any, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_positive_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be positive")
    return parsed
