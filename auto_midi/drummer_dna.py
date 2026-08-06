from __future__ import annotations

from dataclasses import dataclass
import random

from .text_parser import TextMap
from .groove import GROOVE_ANCHORS as GROOVE_TEMPLATE_ANCHORS, GROOVE_PULSES, GROOVE_PROFILES, default_groove
from .style_catalog import STYLE_BOUNDS


FILL_VOCABULARIES = ("snare_roll", "tom_run", "hat_roll", "silence", "mixed")
DYNAMIC_SHAPES = ("flat", "front_heavy", "back_heavy", "crescendo", "decrescendo", "pocket")
GROOVE_ANCHORS = ("strong_one", "one_drop", "four_on_floor", "offbeat_push", "floating")


PRESET_BOUNDS = STYLE_BOUNDS


@dataclass(frozen=True)
class DrummerDNA:
    style: str  # Style boundary used to generate this individual drummer, e.g. reggae, hiphop, jazz. 椋庢牸杈圭晫锛岀敤浜庣敓鎴愯榧撴墜涓綋锛堝 reggae銆乭iphop銆乯azz锛夈€?
    pulse: int  # Main subdivision feel: 4, 8, or 16 steps per bar emphasis. 涓昏缁嗗垎寰嬪姩锛氭瘡灏忚妭浠?4/8/16 姝ヤ负閲嶅績銆?
    low_bias: float  # Kick/low-slot activity tendency. 搴曢紦/浣庨澹伴儴娲昏穬鍊惧悜銆?
    mid_bias: float  # Snare, rim, and clap activity tendency. 鍐涢紦銆乺im銆乧lap 绛変腑棰戝０閮ㄦ椿璺冨€惧悜銆?
    high_density: float  # Hat/cymbal density tendency. 闀茬墖锛坔at/cymbal锛夊瘑搴﹀€惧悜銆?
    backbeat_weight: float  # Stability and strength of snare-like backbeat hits. 鍙嶆媿锛堢被浼煎啗榧撹惤鐐癸級鐨勭ǔ瀹氭€т笌鍔涘害鏉冮噸銆?
    ghost_note_bias: float  # Tendency to add quiet rim/snare ghost notes. 娣诲姞杞诲急 ghost note锛坮im/snare锛夌殑鍊惧悜銆?
    hat_openness: float  # Probability bias toward open hats instead of closed hats. 寮€闀茬浉瀵归棴闀茬殑姒傜巼鍋忓悜銆?
    kick_snare_lock: float  # How strongly kick/snare preserve a traditional groove skeleton. 搴曢紦/鍐涢紦淇濇寔浼犵粺 groove 楠ㄦ灦鐨勫己搴︺€?
    phrase_memory: float  # Chance to reuse material from the previous bar. 澶嶇敤涓婁竴灏忚妭绱犳潗鐨勬鐜囥€?
    accent_follow: float  # How strongly text token starts become drum accents. 鏂囨湰 token 璧峰浣嶇疆杞负閲嶉煶鐨勮窡闅忓己搴︺€?
    rest_follow: float  # How strongly punctuation and phrase breaks create rests. 鏍囩偣涓庤鍙ュ仠椤胯浆涓轰紤姝㈢殑璺熼殢寮哄害銆?
    syncopation: float  # Off-beat and weak-step activity tendency. 鍒囧垎涓庡急鎷嶄綅缃殑娲昏穬鍊惧悜銆?
    repetition: float  # Higher values keep bars more repetitive and loop-like. 鏁板€艰秺楂橈紝灏忚妭瓒婇噸澶嶃€佽秺寰幆鍖栥€?
    mutation: float  # Bar-to-bar variation and text-driven extra event tendency. 灏忚妭闂村彉鍖栦笌鏂囨湰椹卞姩闄勫姞浜嬩欢鐨勫€惧悜銆?
    fill_aggression: float  # Fill probability and density multiplier. Fill锛堝姞鑺憋級鍑虹幇姒傜巼涓庡瘑搴︾殑鍊嶇巼銆?
    fill_vocabulary: str  # Fill language: snare_roll, tom_run, hat_roll, silence, or mixed. Fill 璇█闆嗗悎锛歴nare_roll銆乼om_run銆乭at_roll銆乻ilence 鎴?mixed銆?
    dynamic_shape: str  # Per-bar velocity curve: flat, front_heavy, back_heavy, crescendo, decrescendo, or pocket. 姣忓皬鑺傚姏搴︽洸绾匡細flat銆乫ront_heavy銆乥ack_heavy銆乧rescendo銆乨ecrescendo 鎴?pocket銆?
    groove_anchor: str  # Core groove gravity: strong_one, one_drop, four_on_floor, offbeat_push, or floating. 鏍稿績 groove 閲嶅績锛歴trong_one銆乷ne_drop銆乫our_on_floor銆乷ffbeat_push 鎴?floating銆?
    swing: float  # Timing delay applied to off-steps for swing/shuffle feel. 瀵归潪寮烘媿姝ラ暱鏂藉姞鏃跺€煎欢鍚庯紝浠ュ舰鎴?swing/shuffle 鎰熴€?

    groove: str = "free"
    skeleton_strength: float = 0.5
    backbeat_variation: float = 0.5
    ornament_amount: float = 0.5


def generate_dna(
    text_map: TextMap,
    rng: random.Random,
    complexity: int,
    intensity: int,
    fill: int,
    randomness: int,
    preset: str = "free",
    groove: str | None = None,
) -> DrummerDNA:
    density = min(1.0, text_map.average_chars / 16.0)
    variation = _scale(randomness)
    complexity_value = _scale(complexity)
    intensity_value = _scale(intensity)
    fill_value = _scale(fill)
    bounds = PRESET_BOUNDS.get(preset, PRESET_BOUNDS["free"])
    groove_value = groove or default_groove(preset)
    groove_anchor = GROOVE_TEMPLATE_ANCHORS.get(groove_value)
    groove_profile = GROOVE_PROFILES.get(groove_value, GROOVE_PROFILES["free"])

    pulse = GROOVE_PULSES.get(groove_value, _choose_pulse(rng, density, complexity_value, bounds))
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
        groove_anchor=groove_anchor or _choice(rng, bounds, "groove_anchor", GROOVE_ANCHORS),
        swing=_bounded(rng, bounds, "swing", rng.uniform(0.0, 0.16) * (0.4 + complexity_value), variation),
        groove=groove_value,
        skeleton_strength=_clamp(groove_profile["skeleton_strength"] - variation * 0.20),
        backbeat_variation=_clamp(groove_profile["backbeat_variation"] + variation * 0.35),
        ornament_amount=_clamp(groove_profile["ornament_amount"] + variation * 0.45 + complexity_value * 0.10),
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
