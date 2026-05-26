from __future__ import annotations

from dataclasses import dataclass
import re


PUNCTUATION = set("，。！？；：,.!?;:")
STRONG_ENDINGS = set("。！？.!?")


@dataclass(frozen=True)
class BarText:
    index: int
    section: int
    text: str
    tokens: tuple[str, ...]
    punctuation_positions: tuple[int, ...]
    ends_section: bool = False

    @property
    def char_count(self) -> int:
        return sum(1 for char in self.text if char.strip() and char not in PUNCTUATION)

    @property
    def token_count(self) -> int:
        return len(self.tokens)

    @property
    def has_strong_ending(self) -> bool:
        return any(char in STRONG_ENDINGS for char in self.text[-2:])


@dataclass(frozen=True)
class TextMap:
    bars: tuple[BarText, ...]
    section_count: int

    @property
    def average_chars(self) -> float:
        if not self.bars:
            return 0.0
        return sum(bar.char_count for bar in self.bars) / len(self.bars)

    @property
    def max_chars(self) -> int:
        return max((bar.char_count for bar in self.bars), default=0)


def parse_text(raw: str) -> TextMap:
    bars: list[BarText] = []
    section = 0
    pending_section_break = False

    for line in raw.splitlines():
        text = line.strip()
        if not text:
            if bars:
                pending_section_break = True
            continue

        if pending_section_break:
            previous = bars[-1]
            bars[-1] = BarText(
                index=previous.index,
                section=previous.section,
                text=previous.text,
                tokens=previous.tokens,
                punctuation_positions=previous.punctuation_positions,
                ends_section=True,
            )
            section += 1
            pending_section_break = False

        bars.append(
            BarText(
                index=len(bars),
                section=section,
                text=text,
                tokens=tuple(tokenize(text)),
                punctuation_positions=tuple(find_punctuation_positions(text)),
            )
        )

    if bars:
        previous = bars[-1]
        bars[-1] = BarText(
            index=previous.index,
            section=previous.section,
            text=previous.text,
            tokens=previous.tokens,
            punctuation_positions=previous.punctuation_positions,
            ends_section=True,
        )

    section_count = len({bar.section for bar in bars})
    return TextMap(bars=tuple(bars), section_count=section_count)


def tokenize(text: str) -> list[str]:
    cleaned = "".join(" " if char in PUNCTUATION else char for char in text)
    ascii_words = re.findall(r"[A-Za-z0-9]+", cleaned)
    if ascii_words and len("".join(ascii_words)) > len(cleaned.replace(" ", "")) * 0.5:
        return ascii_words
    return [char for char in cleaned if char.strip()]


def find_punctuation_positions(text: str) -> list[int]:
    positions: list[int] = []
    syllable_index = 0
    for char in text:
        if char in PUNCTUATION:
            positions.append(max(0, syllable_index - 1))
        elif char.strip():
            syllable_index += 1
    return positions
