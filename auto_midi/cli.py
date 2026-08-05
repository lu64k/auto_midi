from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import random

from .drummer_dna import PRESET_BOUNDS, generate_dna
from .groove import default_groove, grooves_for_style
from .midi_exporter import write_midi
from .pattern_generator import generate_events
from .section_config import load_section_config
from .sample_kit import inspect_kit
from .song_structure import apply_song_structure, load_song_structure, section_configs_from_song_structure
from .settings import settings
from .time_signature import SUPPORTED_TIME_SIGNATURES, parse_time_signature
from .text_parser import parse_text
from .wav_preview import render_preview_wav


@dataclass(frozen=True)
class RunConfig:
    input_text_path: str  # UTF-8 lyric/poem text file; one non-empty line is treated as one bar.
    output_midi_path: str  # Output MIDI path; empty string means auto-generate outputs/<input>_drums.mid.
    preview_wav_path: str | None  # WAV preview path; None disables preview, empty string follows MIDI filename.
    sample_kit_path: str  # Folder containing canonical drum samples such as kick.wav and snare.wav.
    preset: str  # Style boundary used to generate DrummerDNA, e.g. reggae, hiphop, jazz, rock.
    groove: str
    time_signature: str
    bpm: int  # Tempo in beats per minute.
    complexity: int  # 0-100; controls event density, subdivisions, and ornamental behavior.
    intensity: int  # 0-100; controls velocity and how assertive core drum hits feel.
    fill: int  # 0-100; controls fill probability and fill aggression.
    randomness: int  # 0-100; controls DNA variation and text-driven mutation amount.
    seed: int | None  # Optional repeatability seed; None generates a random seed for this run.
    print_text_map: bool  # Print NLP tokens, phrase boundaries, syllable spans, pauses, and rhyme keys.


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = config_from_args(args)
    input_path = Path(config.input_text_path)
    raw = input_path.read_text(encoding="utf-8")
    text_map = parse_text(raw)
    if not text_map.bars:
        parser.error("input text does not contain any non-empty lines")
    if config.print_text_map:
        print_text_map(text_map)

    structure = load_song_structure(Path(args.song_structure)) if args.song_structure else None
    if structure:
        try:
            text_map = apply_song_structure(text_map, structure)
        except ValueError as exc:
            parser.error(str(exc))
    effective_bpm = structure.bpm if structure else config.bpm
    effective_time_signature = structure.time_signature if structure else config.time_signature
    try:
        signature = parse_time_signature(effective_time_signature)
    except ValueError as exc:
        parser.error(str(exc))

    seed = random.randrange(1_000_000_000) if config.seed is None or config.seed == -1 else config.seed
    rng = random.Random(seed)
    dna = generate_dna(
        text_map=text_map,
        rng=rng,
        complexity=config.complexity,
        intensity=config.intensity,
        fill=config.fill,
        randomness=config.randomness,
        preset=config.preset,
        groove=config.groove,
    )
    if structure:
        try:
            section_configs = section_configs_from_song_structure(structure, text_map)
        except ValueError as exc:
            parser.error(str(exc))
    else:
        section_configs = load_section_config(Path(args.section_config)) if args.section_config else None
    if section_configs and len(section_configs) != text_map.section_count:
        parser.error(
            f"section config contains {len(section_configs)} sections, "
            f"but input text contains {text_map.section_count}"
        )
    events = generate_events(
        text_map,
        dna,
        rng,
        intensity=config.intensity,
        fill=config.fill,
        section_configs=section_configs,
        time_signature=signature,
    )

    output_path = Path(config.output_midi_path) if config.output_midi_path else settings.output_dir / f"{input_path.stem}_drums.mid"
    write_midi(events, output_path, bpm=effective_bpm, time_signature=signature)

    print(f"Wrote {output_path}")
    if config.preview_wav_path is not None:
        preview_path = Path(config.preview_wav_path) if config.preview_wav_path else output_path.with_suffix(".wav")
        kit_status = inspect_kit(Path(config.sample_kit_path))
        render_preview_wav(
            events=events,
            kit_status=kit_status,
            output_path=preview_path,
            bpm=effective_bpm,
            bar_count=len(text_map.bars),
            time_signature=signature,
        )
        print(f"Wrote {preview_path}")
    print(f"Seed: {seed}")
    print(f"Bars: {len(text_map.bars)}")
    print(f"Preset constraint: {config.preset}")
    if structure:
        print(f"Song structure: {structure.title} ({len(structure.sections)} sections)")
    print(
        "DrummerDNA: "
        f"style={dna.style}, "
        f"pulse={dna.pulse}, "
        f"low={dna.low_bias:.2f}, "
        f"mid={dna.mid_bias:.2f}, "
        f"high={dna.high_density:.2f}, "
        f"backbeat={dna.backbeat_weight:.2f}, "
        f"ghost={dna.ghost_note_bias:.2f}, "
        f"hat_open={dna.hat_openness:.2f}, "
        f"lock={dna.kick_snare_lock:.2f}, "
        f"memory={dna.phrase_memory:.2f}, "
        f"sync={dna.syncopation:.2f}, "
        f"mutation={dna.mutation:.2f}, "
        f"fill_vocab={dna.fill_vocabulary}, "
        f"dynamic={dna.dynamic_shape}, "
        f"anchor={dna.groove_anchor}, "
        f"swing={dna.swing:.2f}"
    )
    return 0


def config_from_args(args: argparse.Namespace) -> RunConfig:
    return RunConfig(
        input_text_path=args.input,
        output_midi_path=args.output or "",
        preview_wav_path=args.preview_wav,
        sample_kit_path=args.sample_kit,
        preset=args.preset,
        groove=args.groove,
        time_signature=args.time_signature,
        bpm=args.bpm,
        complexity=args.complexity,
        intensity=args.intensity,
        fill=args.fill,
        randomness=args.randomness,
        seed=args.seed,
        print_text_map=args.print_text_map,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auto_midi",
        description="Generate a General MIDI drum track from poem/lyric rhythm.",
    )
    parser.add_argument("input", help="UTF-8 text file. One non-empty line is treated as one bar.")
    parser.add_argument("--output", "-o", help="Output .mid path. Defaults to outputs/<input>_drums.mid.")
    parser.add_argument("--bpm", type=_bounded_int(30, 260), default=settings.bpm)
    parser.add_argument("--complexity", type=_bounded_int(0, 100), default=settings.complexity)
    parser.add_argument("--intensity", type=_bounded_int(0, 100), default=settings.intensity)
    parser.add_argument("--fill", type=_bounded_int(0, 100), default=settings.fill)
    parser.add_argument("--randomness", type=_bounded_int(0, 100), default=settings.randomness)
    parser.add_argument("--seed", type=int, help="Set for repeatable generation; use -1 for a new random seed.")
    parser.add_argument("--preset", choices=sorted(PRESET_BOUNDS), default=settings.preset)
    parser.add_argument("--groove", default=settings.groove, help="Named style groove template.")
    parser.add_argument("--time-signature", choices=list(SUPPORTED_TIME_SIGNATURES), default=settings.time_signature)
    parser.add_argument("--section-config", help="JSON file with explicit per-section drum controls.")
    parser.add_argument(
        "--song-structure",
        help="User-authored JSON with section types, bar counts, and section-level chords. "
        "Its BPM and time signature override the matching CLI defaults.",
    )
    parser.add_argument("--print-text-map", action="store_true", help="Print NLP token, phrase, and rhyme analysis.")
    parser.add_argument(
        "--preview-wav",
        nargs="?",
        const="",
        help="Render a WAV preview. Optionally pass the output .wav path.",
    )
    parser.add_argument("--sample-kit", default=str(settings.sample_kit), help="Folder containing canonical drum sample WAVs.")
    return parser


def print_text_map(text_map) -> None:
    print("TextMap:")
    for bar in text_map.bars:
        print(f"  bar={bar.index} section={bar.section} rhyme={bar.rhyme_key} tokens={'/'.join(bar.tokens)}")
        for phrase in bar.phrases:
            token_text = "/".join(token.text for token in phrase.tokens)
            print(
                "    "
                f"phrase={phrase.text} "
                f"tokens={token_text} "
                f"syllables={phrase.start_syllable}-{phrase.end_syllable} "
                f"pause={phrase.pause_strength:.2f} "
                f"rhyme={phrase.rhyme_key}"
            )


def _bounded_int(low: int, high: int):
    def parse(value: str) -> int:
        parsed = int(value)
        if parsed < low or parsed > high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return parsed

    return parse
