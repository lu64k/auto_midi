"""Natural-language requirement parsing for the first Gradio stage."""

from __future__ import annotations

import json
import re

from .llm_client import LLMError
from .song_structure import SongStructure, parse_song_structure


class LLMRequirementsAgent:
    def __init__(self, client):
        self.client = client

    def generate(
        self,
        requirements: str,
        lyrics: str,
        bpm: int,
        time_signature: str,
        seed: int,
    ) -> SongStructure:
        context = {
            "requirements": requirements,
            "lyrics": lyrics,
            "bpm_default": bpm,
            "time_signature_default": time_signature,
        }
        payload = self.client.complete_json(_SYSTEM_PROMPT, json.dumps(context, ensure_ascii=False), seed)
        return parse_song_structure(payload)


def build_requirements_agent():
    from .llm_client import OpenAICompatibleClient
    from .settings import settings

    api_key = settings.llm_api_key()
    if settings.llm_enabled and api_key:
        return LLMRequirementsAgent(
            OpenAICompatibleClient(
                base_url=settings.llm_base_url,
                api_key=api_key,
                model=settings.llm_model,
                timeout=settings.llm_timeout,
            )
        )
    return None


def fallback_song_structure(requirements: str, lyrics: str, bpm: int, time_signature: str) -> SongStructure:
    """Build a conservative structure when the gateway is unavailable."""

    non_empty_lines = [line for line in lyrics.splitlines() if line.strip()]
    total_bars = max(1, len(non_empty_lines))
    matches = re.findall(r"(intro|verse|pre[-_ ]?chorus|chorus|bridge|outro)\s*(\d+)?\s*(?:bars?|小节)?", requirements.lower())
    sections = []
    cursor = 0
    for index, (raw_type, raw_bars) in enumerate(matches, start=1):
        section_type = raw_type.replace("-", "_").replace(" ", "_")
        bars = int(raw_bars) if raw_bars else 0
        if bars <= 0:
            continue
        sections.append(
            {
                "id": f"{section_type}_{index}",
                "type": section_type,
                "index": index,
                "bars": bars,
                "lyrics_start": cursor + 1,
                "lyrics_end": cursor + bars,
                "chords": [],
            }
        )
        cursor += bars
    if not sections or cursor != total_bars:
        sections = [
            {
                "id": "verse_1",
                "type": "verse",
                "index": 1,
                "bars": total_bars,
                "lyrics_start": 1,
                "lyrics_end": total_bars,
                "chords": [],
            }
        ]
    return parse_song_structure(
        {
            "title": "untitled",
            "bpm": bpm,
            "time_signature": time_signature,
            "sections": sections,
        }
    )


_SYSTEM_PROMPT = """You are a song-requirements parser. Return JSON only.
Turn the user's natural-language music requirements and lyrics into an authored
song structure. Do not invent chord progressions: use chords only when the
user explicitly provides them. The output must contain title, bpm,
time_signature, optional key, and sections. Every section must contain id,
type, bars, lyrics_start, lyrics_end, and chords as a per-bar nested list or
[]. Valid section types: intro, verse, pre_chorus, chorus, bridge,
instrumental, outro. The sum of bars must equal the number of non-empty lyric
lines. Return exactly the root object, no Markdown fences."""
