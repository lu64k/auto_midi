from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
import wave

from .pattern_generator import DrumEvent, STEPS_PER_BAR
from .sample_kit import KitStatus


SAMPLE_RATE = 44_100


@dataclass(frozen=True)
class AudioSample:
    frames: tuple[float, ...]
    sample_rate: int


def render_preview_wav(
    events: list[DrumEvent],
    kit_status: KitStatus,
    output_path: Path,
    bpm: int,
    bar_count: int,
) -> None:
    if not kit_status.ready:
        missing = ", ".join(kit_status.missing)
        raise FileNotFoundError(f"sample kit is missing required files: {missing}")

    samples = {
        voice: _load_sample(path)
        for voice, path in kit_status.samples.items()
    }
    seconds_per_step = 60.0 / bpm / 4.0
    total_frames = int((bar_count * STEPS_PER_BAR * seconds_per_step + 2.0) * SAMPLE_RATE)
    mix = [0.0] * total_frames

    for event in events:
        sample = samples.get(event.voice)
        if sample is None:
            continue
        start_seconds = event.bar * STEPS_PER_BAR * seconds_per_step + event.step * seconds_per_step
        start_seconds += event.offset_ticks / 480.0 * (60.0 / bpm)
        start = max(0, int(start_seconds * SAMPLE_RATE))
        gain = (event.velocity / 127.0) ** 1.35
        frames = _resample(sample.frames, sample.sample_rate, SAMPLE_RATE)
        for index, value in enumerate(frames):
            target = start + index
            if target >= total_frames:
                break
            mix[target] += value * gain

    peak = max((abs(value) for value in mix), default=0.0)
    if peak > 0.98:
        mix = [value * (0.98 / peak) for value in mix]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(b"".join(_float_to_i16(value) for value in mix))


def _load_sample(path: Path) -> AudioSample:
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        raw = wav_file.readframes(wav_file.getnframes())
    values = _decode_pcm(raw, width)
    if channels > 1:
        mono = []
        for index in range(0, len(values), channels):
            mono.append(sum(values[index : index + channels]) / channels)
        values = mono
    return AudioSample(frames=tuple(values), sample_rate=sample_rate)


def _decode_pcm(raw: bytes, width: int) -> list[float]:
    if width == 1:
        return [(byte - 128) / 128.0 for byte in raw]
    if width == 2:
        count = len(raw) // 2
        return [value / 32768.0 for value in struct.unpack(f"<{count}h", raw)]
    if width == 3:
        values = []
        for index in range(0, len(raw), 3):
            chunk = raw[index : index + 3]
            sign = b"\xff" if chunk[2] & 0x80 else b"\x00"
            values.append(int.from_bytes(chunk + sign, "little", signed=True) / 8_388_608.0)
        return values
    if width == 4:
        count = len(raw) // 4
        return [value / 2_147_483_648.0 for value in struct.unpack(f"<{count}i", raw)]
    raise ValueError(f"unsupported sample width: {width}")


def _resample(frames: tuple[float, ...], source_rate: int, target_rate: int) -> tuple[float, ...]:
    if source_rate == target_rate:
        return frames
    if not frames:
        return ()
    ratio = source_rate / target_rate
    target_length = int(len(frames) / ratio)
    result = []
    for index in range(target_length):
        position = index * ratio
        left = int(position)
        right = min(left + 1, len(frames) - 1)
        fraction = position - left
        result.append(frames[left] * (1.0 - fraction) + frames[right] * fraction)
    return tuple(result)


def _float_to_i16(value: float) -> bytes:
    clipped = max(-1.0, min(1.0, value))
    return struct.pack("<h", int(clipped * 32767))
