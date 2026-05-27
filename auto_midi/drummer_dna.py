from __future__ import annotations

from dataclasses import dataclass
import random

from .text_parser import TextMap


FILL_VOCABULARIES = ("snare_roll", "tom_run", "hat_roll", "silence", "mixed")
DYNAMIC_SHAPES = ("flat", "front_heavy", "back_heavy", "crescendo", "decrescendo", "pocket")
GROOVE_ANCHORS = ("strong_one", "one_drop", "four_on_floor", "offbeat_push", "floating")


PRESET_BOUNDS = {
    "free": {},
    "boom_bap": {
        "swing": (0.08, 0.22),
        "syncopation": (0.25, 0.6),
        "high_density": (0.35, 0.7),
        "mid_bias": (0.6, 0.95),
        "backbeat_weight": (0.7, 1.0),
        "ghost_note_bias": (0.25, 0.65),
        "hat_openness": (0.02, 0.18),
        "kick_snare_lock": (0.55, 0.9),
        "phrase_memory": (0.55, 0.9),
        "fill_vocabulary": ("snare_roll", "mixed"),
        "dynamic_shape": ("pocket", "front_heavy"),
        "groove_anchor": ("strong_one", "floating", "offbeat_push"),
    },
    "hiphop": {
        "swing": (0.06, 0.2),
        "syncopation": (0.25, 0.65),
        "high_density": (0.25, 0.7),
        "backbeat_weight": (0.65, 1.0),
        "ghost_note_bias": (0.25, 0.7),
        "hat_openness": (0.02, 0.2),
        "kick_snare_lock": (0.45, 0.85),
        "phrase_memory": (0.55, 0.9),
        "fill_vocabulary": ("snare_roll", "mixed", "silence"),
        "dynamic_shape": ("pocket", "flat", "front_heavy"),
        "groove_anchor": ("strong_one", "floating", "offbeat_push"),
    },
    "trap": {
        "pulse": (16, 16),
        "swing": (0.0, 0.08),
        "syncopation": (0.45, 0.9),
        "high_density": (0.55, 1.0),
        "low_bias": (0.55, 0.95),
        "backbeat_weight": (0.45, 0.8),
        "ghost_note_bias": (0.05, 0.35),
        "hat_openness": (0.05, 0.25),
        "kick_snare_lock": (0.25, 0.65),
        "phrase_memory": (0.35, 0.75),
        "fill_vocabulary": ("hat_roll", "snare_roll", "mixed"),
        "dynamic_shape": ("flat", "back_heavy", "crescendo"),
        "groove_anchor": ("floating", "strong_one", "offbeat_push"),
    },
    "minimal": {
        "syncopation": (0.05, 0.35),
        "high_density": (0.1, 0.45),
        "mutation": (0.05, 0.3),
        "backbeat_weight": (0.25, 0.7),
        "ghost_note_bias": (0.0, 0.25),
        "hat_openness": (0.0, 0.12),
        "kick_snare_lock": (0.25, 0.75),
        "phrase_memory": (0.7, 1.0),
        "fill_vocabulary": ("silence", "snare_roll"),
        "dynamic_shape": ("flat", "decrescendo"),
        "groove_anchor": ("floating", "strong_one"),
    },
    "rock": {
        "pulse": (8, 16),
        "swing": (0.0, 0.05),
        "syncopation": (0.1, 0.35),
        "low_bias": (0.65, 1.0),
        "mid_bias": (0.7, 1.0),
        "backbeat_weight": (0.8, 1.0),
        "ghost_note_bias": (0.05, 0.35),
        "hat_openness": (0.08, 0.35),
        "kick_snare_lock": (0.7, 1.0),
        "phrase_memory": (0.45, 0.8),
        "fill_vocabulary": ("tom_run", "snare_roll", "mixed"),
        "dynamic_shape": ("front_heavy", "crescendo", "flat"),
        "groove_anchor": ("strong_one", "four_on_floor"),
    },
    "jazz": {
        "pulse": (8, 16),
        "swing": (0.12, 0.32),
        "syncopation": (0.55, 1.0),
        "low_bias": (0.15, 0.55),
        "mid_bias": (0.35, 0.75),
        "high_density": (0.55, 0.95),
        "backbeat_weight": (0.1, 0.55),
        "ghost_note_bias": (0.55, 1.0),
        "hat_openness": (0.18, 0.55),
        "kick_snare_lock": (0.05, 0.4),
        "phrase_memory": (0.25, 0.65),
        "fill_vocabulary": ("snare_roll", "silence", "mixed"),
        "dynamic_shape": ("pocket", "crescendo", "decrescendo"),
        "groove_anchor": ("floating", "offbeat_push"),
    },
    "country": {
        "pulse": (8, 16),
        "swing": (0.03, 0.16),
        "syncopation": (0.1, 0.4),
        "low_bias": (0.55, 0.9),
        "mid_bias": (0.55, 0.9),
        "high_density": (0.35, 0.75),
        "backbeat_weight": (0.6, 0.95),
        "ghost_note_bias": (0.05, 0.35),
        "hat_openness": (0.03, 0.22),
        "kick_snare_lock": (0.65, 0.95),
        "phrase_memory": (0.6, 0.9),
        "fill_vocabulary": ("snare_roll", "tom_run"),
        "dynamic_shape": ("flat", "front_heavy"),
        "groove_anchor": ("strong_one", "four_on_floor"),
    },
    "funk": {
        "pulse": (16, 16),
        "swing": (0.02, 0.14),
        "syncopation": (0.55, 0.95),
        "low_bias": (0.45, 0.85),
        "mid_bias": (0.55, 0.95),
        "high_density": (0.55, 0.95),
        "backbeat_weight": (0.55, 0.9),
        "ghost_note_bias": (0.55, 1.0),
        "hat_openness": (0.12, 0.45),
        "kick_snare_lock": (0.35, 0.75),
        "phrase_memory": (0.55, 0.9),
        "fill_vocabulary": ("snare_roll", "hat_roll", "mixed"),
        "dynamic_shape": ("pocket", "flat"),
        "groove_anchor": ("offbeat_push", "strong_one", "floating"),
    },
    "reggae": {
        "pulse": (8, 16),
        "swing": (0.08, 0.22),
        "syncopation": (0.45, 0.85),
        "low_bias": (0.3, 0.7),
        "mid_bias": (0.45, 0.85),
        "high_density": (0.25, 0.65),
        "backbeat_weight": (0.2, 0.6),
        "ghost_note_bias": (0.2, 0.65),
        "hat_openness": (0.15, 0.55),
        "kick_snare_lock": (0.1, 0.45),
        "phrase_memory": (0.55, 0.9),
        "fill_vocabulary": ("silence", "snare_roll", "mixed"),
        "dynamic_shape": ("back_heavy", "pocket", "flat"),
        "groove_anchor": ("one_drop",),
    },
}


@dataclass(frozen=True)
class DrummerDNA:
    style: str  # Style boundary used to generate this individual drummer, e.g. reggae, hiphop, jazz. 风格边界，用于生成该鼓手个体（如 reggae、hiphop、jazz）。
    pulse: int  # Main subdivision feel: 4, 8, or 16 steps per bar emphasis. 主要细分律动：每小节以 4/8/16 步为重心。
    low_bias: float  # Kick/low-slot activity tendency. 底鼓/低频声部活跃倾向。
    mid_bias: float  # Snare, rim, and clap activity tendency. 军鼓、rim、clap 等中频声部活跃倾向。
    high_density: float  # Hat/cymbal density tendency. 镲片（hat/cymbal）密度倾向。
    backbeat_weight: float  # Stability and strength of snare-like backbeat hits. 反拍（类似军鼓落点）的稳定性与力度权重。
    ghost_note_bias: float  # Tendency to add quiet rim/snare ghost notes. 添加轻弱 ghost note（rim/snare）的倾向。
    hat_openness: float  # Probability bias toward open hats instead of closed hats. 开镲相对闭镲的概率偏向。
    kick_snare_lock: float  # How strongly kick/snare preserve a traditional groove skeleton. 底鼓/军鼓保持传统 groove 骨架的强度。
    phrase_memory: float  # Chance to reuse material from the previous bar. 复用上一小节素材的概率。
    accent_follow: float  # How strongly text token starts become drum accents. 文本 token 起始位置转为重音的跟随强度。
    rest_follow: float  # How strongly punctuation and phrase breaks create rests. 标点与语句停顿转为休止的跟随强度。
    syncopation: float  # Off-beat and weak-step activity tendency. 切分与弱拍位置的活跃倾向。
    repetition: float  # Higher values keep bars more repetitive and loop-like. 数值越高，小节越重复、越循环化。
    mutation: float  # Bar-to-bar variation and text-driven extra event tendency. 小节间变化与文本驱动附加事件的倾向。
    fill_aggression: float  # Fill probability and density multiplier. Fill（加花）出现概率与密度的倍率。
    fill_vocabulary: str  # Fill language: snare_roll, tom_run, hat_roll, silence, or mixed. Fill 语言集合：snare_roll、tom_run、hat_roll、silence 或 mixed。
    dynamic_shape: str  # Per-bar velocity curve: flat, front_heavy, back_heavy, crescendo, decrescendo, or pocket. 每小节力度曲线：flat、front_heavy、back_heavy、crescendo、decrescendo 或 pocket。
    groove_anchor: str  # Core groove gravity: strong_one, one_drop, four_on_floor, offbeat_push, or floating. 核心 groove 重心：strong_one、one_drop、four_on_floor、offbeat_push 或 floating。
    swing: float  # Timing delay applied to off-steps for swing/shuffle feel. 对非强拍步长施加时值延后，以形成 swing/shuffle 感。


def generate_dna(
    text_map: TextMap,
    rng: random.Random,
    complexity: int,
    intensity: int,
    fill: int,
    randomness: int,
    preset: str = "free",
) -> DrummerDNA:
    density = min(1.0, text_map.average_chars / 16.0)
    variation = _scale(randomness)
    complexity_value = _scale(complexity)
    intensity_value = _scale(intensity)
    fill_value = _scale(fill)
    bounds = PRESET_BOUNDS.get(preset, PRESET_BOUNDS["free"])

    pulse = _choose_pulse(rng, density, complexity_value, bounds)
    return DrummerDNA(
        style=preset,
        pulse=pulse,
        low_bias=_bounded(rng, bounds, "low_bias", 0.35 + intensity_value * 0.45, variation),
        mid_bias=_bounded(rng, bounds, "mid_bias", 0.45 + intensity_value * 0.35, variation),
        high_density=_bounded(rng, bounds, "high_density", 0.2 + complexity_value * 0.65 + density * 0.15, variation),
        backbeat_weight=_bounded(rng, bounds, "backbeat_weight", 0.45 + intensity_value * 0.4, variation),
        ghost_note_bias=_bounded(rng, bounds, "ghost_note_bias", 0.1 + complexity_value * 0.45, variation),
        hat_openness=_bounded(rng, bounds, "hat_openness", 0.05 + complexity_value * 0.25, variation),
        kick_snare_lock=_bounded(rng, bounds, "kick_snare_lock", 0.35 + intensity_value * 0.35, variation),
        phrase_memory=_bounded(rng, bounds, "phrase_memory", 0.65 - variation * 0.25, variation),
        accent_follow=_clamp(0.35 + density * 0.35 + variation * 0.25),
        rest_follow=_clamp(0.25 + variation * 0.45),
        syncopation=_bounded(rng, bounds, "syncopation", 0.15 + complexity_value * 0.45, variation),
        repetition=_clamp(0.75 - variation * 0.5 + rng.uniform(-0.1, 0.1)),
        mutation=_bounded(rng, bounds, "mutation", 0.1 + variation * 0.55, variation),
        fill_aggression=_clamp(fill_value * (0.4 + complexity_value * 0.6) + rng.uniform(-0.1, 0.1)),
        fill_vocabulary=_choice(rng, bounds, "fill_vocabulary", FILL_VOCABULARIES),
        dynamic_shape=_choice(rng, bounds, "dynamic_shape", DYNAMIC_SHAPES),
        groove_anchor=_choice(rng, bounds, "groove_anchor", GROOVE_ANCHORS),
        swing=_bounded(rng, bounds, "swing", rng.uniform(0.0, 0.16) * (0.4 + complexity_value), variation),
    )


def _choose_pulse(
    rng: random.Random,
    density: float,
    complexity: float,
    bounds: dict[str, tuple[float, float]],
) -> int:
    if "pulse" in bounds:
        low, high = bounds["pulse"]
        return int(rng.choice([int(low), int(high)]))
    if density > 0.8 or complexity > 0.65:
        return rng.choice([16, 16, 8])
    if complexity < 0.25:
        return rng.choice([4, 8])
    return rng.choice([8, 16])


def _bounded(
    rng: random.Random,
    bounds: dict[str, tuple[float, float]],
    key: str,
    center: float,
    variation: float,
) -> float:
    if key in bounds:
        low, high = bounds[key]
        return rng.uniform(low, high)
    spread = 0.15 + variation * 0.35
    return _clamp(rng.uniform(center - spread, center + spread))


def _choice(
    rng: random.Random,
    bounds: dict[str, tuple[float, float] | tuple[str, ...]],
    key: str,
    options: tuple[str, ...],
) -> str:
    value = bounds.get(key)
    if value:
        return rng.choice(tuple(str(item) for item in value))
    return rng.choice(options)


def _scale(value: int) -> float:
    return _clamp(value / 100.0)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
