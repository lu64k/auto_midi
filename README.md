# Auto Midi

Text-driven MIDI drum sketch generator.

This first version reads a poem/lyric text file, treats each non-empty line as
one bar, generates a temporary `DrummerDNA` from the text, and exports a
General MIDI drum track.

## Quick Start

```bash
python3 -m auto_midi examples/poem.txt --bpm 92 --seed 42
```

The MIDI file will be written to:

```text
outputs/poem_drums.mid
```

## WAV Preview With A Classic Kit

This repo can render a quick WAV preview from local drum samples. The sample
files are intentionally ignored by git.

Download the Judd Madden drum sample pack from:

```text
https://juddmadden.com/drum-samples.html
```

Then prepare the canonical kit folder:

```bash
python3 scripts/prepare_judd_kit.py /path/to/judd-madden-drums.zip
```

Or, if you already extracted it:

```bash
python3 scripts/prepare_judd_kit.py /path/to/extracted/drum-samples
```

Render MIDI and WAV together:

```bash
python3 -m auto_midi examples/poem.txt --bpm 92 --seed 42 --preview-wav
```

Expected local files:

```text
samples/classic_kit/kick.wav
samples/classic_kit/snare.wav
samples/classic_kit/closed_hat.wav
samples/classic_kit/open_hat.wav
samples/classic_kit/low_tom.wav
samples/classic_kit/mid_tom.wav
samples/classic_kit/crash.wav
```

## Text Format

- One non-empty line = one bar.
- Empty lines = section breaks.
- Punctuation influences rests, accents, and fill probability.

```text
我在城市边缘听见雨声
夜色落下来像旧的回声

风穿过霓虹和破碎玻璃
我把名字藏进下一次呼吸
```

## Useful Options

```bash
python3 -m auto_midi examples/poem.txt \
  --bpm 88 \
  --complexity 65 \
  --intensity 70 \
  --fill 45 \
  --randomness 35 \
  --seed 7 \
  --preset reggae \
  --output outputs/take_7.mid
```

Available style constraints:

```text
free
boom_bap
hiphop
trap
minimal
rock
jazz
country
funk
reggae
```

Presets are style boundaries for generating a new drummer DNA. They are not
fixed drum patterns.

## Concept

The core loop is:

```text
text sections -> TextMap -> generated DrummerDNA -> drum events -> MIDI
```

Presets are intentionally light. They act as loose constraints for generating a
new drummer, not as fixed drum patterns.

## DrummerDNA v2

Each run generates a temporary drummer profile:

```text
pulse              main grid feel: 4 / 8 / 16
low_bias           kick activity
mid_bias           snare/rim/clap activity
high_density       hat/cymbal density
backbeat_weight    2 and 4 snare stability
ghost_note_bias    quiet snare/rim detail
hat_openness       closed hat vs open hat tendency
kick_snare_lock    traditional kick/snare groove skeleton
phrase_memory      reuse of previous-bar material
syncopation        off-beat and weak-step tendency
mutation           bar-to-bar variation
fill_vocabulary    snare_roll / tom_run / hat_roll / silence / mixed
dynamic_shape      flat / front_heavy / back_heavy / crescendo / decrescendo / pocket
groove_anchor      strong_one / one_drop / four_on_floor / offbeat_push / floating
swing              delayed off-step feel
```
