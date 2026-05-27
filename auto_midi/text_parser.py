from __future__ import annotations

from dataclasses import dataclass
import re

try:
    import jieba
except ImportError:  # pragma: no cover - exercised when optional deps are absent.
    jieba = None

try:
    from pypinyin import Style, lazy_pinyin
except ImportError:  # pragma: no cover - exercised when optional deps are absent.
    Style = None
    lazy_pinyin = None


PUNCTUATION = set("，。！？；：,.!?;:")
STRONG_ENDINGS = set("。！？.!?")
PHRASE_BREAKS = set("，；：,;:")
SENTENCE_ENDINGS = set("。！？.!?")


@dataclass(frozen=True)
class TextToken:
    text: str  # NLP token text, usually a Chinese word or an ASCII word.
    syllables: int  # Estimated syllable count; Chinese uses one syllable per character.
    start_syllable: int  # Inclusive syllable offset inside the bar.
    end_syllable: int  # Exclusive syllable offset inside the bar.
    weight: float  # Accent weight derived from token length.


@dataclass(frozen=True)
class Phrase:
    text: str  # Phrase text split by punctuation or line boundaries.
    tokens: tuple[TextToken, ...]  # Tokens inside this phrase.
    start_syllable: int  # Inclusive phrase syllable offset inside the bar.
    end_syllable: int  # Exclusive phrase syllable offset inside the bar.
    pause_strength: float  # 0-1 pause implied after this phrase.
    rhyme_key: str | None  # Rhyme final for the phrase ending, when available.


@dataclass(frozen=True)
class BarText:
    index: int  # Zero-based bar index.
    section: int  # Section index split by blank lines.
    text: str  # Original line text for this bar.
    tokens: tuple[str, ...]  # Token text strings for quick display and summaries.
    token_units: tuple[TextToken, ...]  # Rich NLP token units used for rhythm mapping.
    phrases: tuple[Phrase, ...]  # Phrase-level cuts, pauses, and rhyme keys.
    punctuation_positions: tuple[int, ...]  # Punctuation offsets in syllable space.
    rhyme_key: str | None = None  # Rhyme final for the full bar ending, when available.
    ends_section: bool = False  # True when this bar ends a blank-line section.

    @property
    def char_count(self) -> int:
        return sum(token.syllables for token in self.token_units)

    @property
    def token_count(self) -> int:
        return len(self.tokens)

    @property
    def has_strong_ending(self) -> bool:
        return any(char in STRONG_ENDINGS for char in self.text[-2:])


@dataclass(frozen=True)
class TextMap:
    bars: tuple[BarText, ...]  # Parsed bars from the source text.
    section_count: int  # Number of blank-line sections in the source text.

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
                token_units=previous.token_units,
                phrases=previous.phrases,
                punctuation_positions=previous.punctuation_positions,
                rhyme_key=previous.rhyme_key,
                ends_section=True,
            )
            section += 1
            pending_section_break = False

        bars.append(analyze_bar(text=text, index=len(bars), section=section))

    if bars:
        previous = bars[-1]
        bars[-1] = BarText(
            index=previous.index,
            section=previous.section,
            text=previous.text,
            tokens=previous.tokens,
            token_units=previous.token_units,
            phrases=previous.phrases,
            punctuation_positions=previous.punctuation_positions,
            rhyme_key=previous.rhyme_key,
            ends_section=True,
        )

    section_count = len({bar.section for bar in bars})
    return TextMap(bars=tuple(bars), section_count=section_count)


def analyze_bar(text: str, index: int, section: int) -> BarText:
    phrases = tuple(split_phrases(text))
    token_units: list[TextToken] = []
    analyzed_phrases: list[Phrase] = []
    syllable_cursor = 0

    for phrase_text, pause_strength in phrases:
        phrase_tokens: list[TextToken] = []
        phrase_start = syllable_cursor
        for token_text in tokenize(phrase_text):
            syllables = count_syllables(token_text)
            weight = token_weight(token_text, syllables)
            token = TextToken(
                text=token_text,
                syllables=syllables,
                start_syllable=syllable_cursor,
                end_syllable=syllable_cursor + syllables,
                weight=weight,
            )
            phrase_tokens.append(token)
            token_units.append(token)
            syllable_cursor += syllables

        if phrase_tokens:
            analyzed_phrases.append(
                Phrase(
                    text=phrase_text,
                    tokens=tuple(phrase_tokens),
                    start_syllable=phrase_start,
                    end_syllable=syllable_cursor,
                    pause_strength=pause_strength,
                    rhyme_key=rhyme_key(phrase_text),
                )
            )

    return BarText(
        index=index,
        section=section,
        text=text,
        tokens=tuple(token.text for token in token_units),
        token_units=tuple(token_units),
        phrases=tuple(analyzed_phrases),
        punctuation_positions=tuple(find_punctuation_positions(text)),
        rhyme_key=rhyme_key(text),
    )


def split_phrases(text: str) -> list[tuple[str, float]]:
    phrases: list[tuple[str, float]] = []
    current: list[str] = []
    for char in text:
        if char in PUNCTUATION:
            phrase = "".join(current).strip()
            if phrase:
                phrases.append((phrase, pause_strength(char)))
            current = []
        else:
            current.append(char)
    phrase = "".join(current).strip()
    if phrase:
        phrases.append((phrase, 0.0))
    return phrases or [(text, 0.0)]


def pause_strength(char: str) -> float:
    if char in SENTENCE_ENDINGS:
        return 1.0
    if char in PHRASE_BREAKS:
        return 0.55
    return 0.25


def tokenize(text: str) -> list[str]:
    cleaned = "".join(" " if char in PUNCTUATION else char for char in text)
    ascii_words = re.findall(r"[A-Za-z0-9]+", cleaned)
    if ascii_words and len("".join(ascii_words)) > len(cleaned.replace(" ", "")) * 0.5:
        return ascii_words
    if jieba is not None:
        tokens = [token.strip() for token in jieba.cut(cleaned) if token.strip()]
        if tokens:
            return tokens
    return [char for char in cleaned if char.strip()]


def count_syllables(text: str) -> int:
    if re.fullmatch(r"[A-Za-z0-9]+", text):
        return max(1, _count_ascii_syllables(text))
    return sum(1 for char in text if char.strip() and char not in PUNCTUATION)


def token_weight(text: str, syllables: int) -> float:
    if syllables >= 3:
        return 1.0
    if syllables == 2:
        return 0.85
    return 0.65


def rhyme_key(text: str) -> str | None:
    last = last_word_char(text)
    if not last:
        return None
    if lazy_pinyin is None or Style is None:
        return last.lower()
    finals = lazy_pinyin(last, style=Style.FINALS, errors="ignore")
    return finals[0] if finals else last.lower()


def last_word_char(text: str) -> str | None:
    for char in reversed(text):
        if char.strip() and char not in PUNCTUATION:
            return char
    return None


def find_punctuation_positions(text: str) -> list[int]:
    positions: list[int] = []
    syllable_index = 0
    for char in text:
        if char in PUNCTUATION:
            positions.append(max(0, syllable_index - 1))
        elif char.strip():
            syllable_index += 1
    return positions


def _count_ascii_syllables(word: str) -> int:
    groups = re.findall(r"[aeiouy]+", word.lower())
    count = len(groups)
    if word.lower().endswith("e") and count > 1:
        count -= 1
    return count or 1
