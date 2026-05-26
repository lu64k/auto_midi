from __future__ import annotations

import argparse
from pathlib import Path
import random

from .drummer_dna import PRESET_BOUNDS, generate_dna
from .midi_exporter import write_midi
from .pattern_generator import generate_events
from .sample_kit import inspect_kit
from .text_parser import parse_text
from .wav_preview import render_preview_wav


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    raw = input_path.read_text(encoding="utf-8")
    text_map = parse_text(raw)
    if not text_map.bars:
        parser.error("input text does not contain any non-empty lines")

    seed = args.seed if args.seed is not None else random.randrange(1_000_000_000)
    rng = random.Random(seed)
    dna = generate_dna(
        text_map=text_map,
        rng=rng,
        complexity=args.complexity,
        intensity=args.intensity,
        fill=args.fill,
        randomness=args.randomness,
        preset=args.preset,
    )
    events = generate_events(text_map, dna, rng, intensity=args.intensity, fill=args.fill)

    output_path = Path(args.output) if args.output else Path("outputs") / f"{input_path.stem}_drums.mid"
    write_midi(events, output_path, bpm=args.bpm)

    print(f"Wrote {output_path}")
    if args.preview_wav is not None:
        preview_path = Path(args.preview_wav) if args.preview_wav else output_path.with_suffix(".wav")
        kit_status = inspect_kit(Path(args.sample_kit))
        render_preview_wav(
            events=events,
            kit_status=kit_status,
            output_path=preview_path,
            bpm=args.bpm,
            bar_count=len(text_map.bars),
        )
        print(f"Wrote {preview_path}")
    print(f"Seed: {seed}")
    print(f"Bars: {len(text_map.bars)}")
    print(f"Preset constraint: {args.preset}")
    print(
        "DrummerDNA: "
        f"pulse={dna.pulse}, "
        f"low={dna.low_bias:.2f}, "
        f"mid={dna.mid_bias:.2f}, "
        f"high={dna.high_density:.2f}, "
        f"sync={dna.syncopation:.2f}, "
        f"mutation={dna.mutation:.2f}, "
        f"swing={dna.swing:.2f}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auto_midi",
        description="Generate a General MIDI drum track from poem/lyric rhythm.",
    )
    parser.add_argument("input", help="UTF-8 text file. One non-empty line is treated as one bar.")
    parser.add_argument("--output", "-o", help="Output .mid path. Defaults to outputs/<input>_drums.mid.")
    parser.add_argument("--bpm", type=_bounded_int(30, 260), default=92)
    parser.add_argument("--complexity", type=_bounded_int(0, 100), default=55)
    parser.add_argument("--intensity", type=_bounded_int(0, 100), default=65)
    parser.add_argument("--fill", type=_bounded_int(0, 100), default=35)
    parser.add_argument("--randomness", type=_bounded_int(0, 100), default=45)
    parser.add_argument("--seed", type=int, help="Set for repeatable generation.")
    parser.add_argument("--preset", choices=sorted(PRESET_BOUNDS), default="free")
    parser.add_argument(
        "--preview-wav",
        nargs="?",
        const="",
        help="Render a WAV preview. Optionally pass the output .wav path.",
    )
    parser.add_argument("--sample-kit", default="samples/classic_kit", help="Folder containing canonical drum sample WAVs.")
    return parser


def _bounded_int(low: int, high: int):
    def parse(value: str) -> int:
        parsed = int(value)
        if parsed < low or parsed > high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return parsed

    return parse
