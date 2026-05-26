from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import zipfile

from auto_midi.sample_kit import REQUIRED_VOICES, prepare_kit


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a local classic drum kit from the Judd Madden sample pack.")
    parser.add_argument("source", help="Path to the downloaded zip file or extracted sample folder.")
    parser.add_argument("--target", default="samples/classic_kit", help="Canonical output kit folder.")
    args = parser.parse_args()

    source = Path(args.source)
    target = Path(args.target)
    if source.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(source) as archive:
                archive.extractall(temp_dir)
            status = prepare_kit(Path(temp_dir), target)
    else:
        status = prepare_kit(source, target)

    print(f"Prepared kit: {status.kit_dir}")
    for voice in REQUIRED_VOICES:
        state = "ok" if voice not in status.missing else "missing"
        print(f"{voice}: {state}")
    if status.missing:
        missing = ", ".join(status.missing)
        raise SystemExit(f"Missing required voices: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
