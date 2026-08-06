# Auto Midi

Text-driven MIDI drum sketch generator.

This first version reads a poem/lyric text file, treats each non-empty line as
one bar, generates a temporary `DrummerDNA` from the text, and exports a
General MIDI drum track.

## Quick Start

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m auto_midi examples/poem.txt --bpm 92 --seed 42
```

### Local environment

Copy `.env.example` to `.env` and adjust the local defaults. The CLI and
Gradio app load `.env` automatically; explicit CLI options take precedence.
Paths in `.env` are relative to the project root.

```bash
cp .env.example .env
```

The main settings are `AUTO_MIDI_*` for generation defaults and
`GRADIO_SERVER_*` for the web app server.

The MIDI file will be written to:

```text
outputs/poem_drums.mid
```

Use a fixed `--seed` to reproduce a take. Use `--seed -1` (or leave it out)
to generate a new random seed; the actual seed is printed in the result.

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
.venv/bin/python -m auto_midi examples/poem.txt --bpm 92 --seed 42 --preview-wav
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
  --time-signature 4/4 \
  --groove classic_rock \
  --complexity 65 \
  --intensity 70 \
  --fill 45 \
  --randomness 35 \
  --seed 7 \
  --preset reggae \
  --output outputs/take_7.mid
```

Inspect the NLP rhythm map:

```bash
.venv/bin/python -m auto_midi examples/poem.txt --print-text-map --seed 42
```

### User-authored song structure

For explicit sections and chord context, pass a structure JSON:

```bash
.venv/bin/python -m auto_midi examples/poem.txt \
  --song-structure examples/song_structure.json \
  --preset rock --groove classic_rock --seed 42
```

Song-structure mode can compile the section feelings through the Agent layer:

```bash
.venv/bin/python -m auto_midi examples/poem.txt \
  --song-structure examples/song_structure.json \
  --agent auto --agent-output outputs/agent.json
```

Use `--agent rule` to stay fully local, or `--agent off` to use only the
user-authored structure. `--agent auto` tries the configured LLM and falls back
to the deterministic rule agent when the gateway is unavailable.

The structure JSON owns the song-level BPM and time signature when supplied.
Chords belong to each section, and each nested chord list maps to one bar;
`"chords": []` means that section has no chord context. The generator does
not invent or carry chords into an unannotated section. `repeat_of` can be used
to explicitly reuse another section's chords.

The Gradio app exposes the same structure JSON as an optional input. When it is
empty, the existing manual drum execution config remains available.

In Gradio, the recommended flow is:

```text
natural-language requirements + lyrics
  -> Read requirements: structure JSON + Drum Feel JSON
  -> Generate execution form: executable section JSON
  -> Generate drums: MIDI/WAV
```

Both intermediate JSON blocks are editable before the next button is pressed.

The second Agent routes two separate levels: one song-level `style`, then a
`groove` skeleton for the sections. `free` is available at both levels. The
router starts with one global groove and only creates a section override for a
real rhythmic-identity change such as half-time, shuffle, or one-drop; ordinary
energy, fill, cymbal, and density changes keep the same groove.

`使用执行配置中的风格与节奏型` controls which source wins during rendering:

- checked: use the routed style and grooves stored in the editable execution
  JSON;
- unchecked: use the current UI style/groove controls. A fixed UI groove is
  applied to all sections, while `free` accepts the Agent's resolved route.

The live style catalog is `auto_midi/catalog/drum_styles.json`. It is the
single source for the UI choices, routing Skill context, DNA bounds, groove
profiles, and explicit step patterns. The process checks it for changes every
five seconds and swaps in a valid update atomically, so adding a style or
groove there does not require restarting Gradio. Invalid edits leave the last
valid catalog active and produce a warning.

### Internal LLM gateway

When the system environment variable `10086` is available, the Gradio structure
mode uses the configured OpenAI-compatible gateway for Drum Feel generation:

```text
AUTO_MIDI_LLM_BASE_URL=http://gpus.pixo.local:10086/v1
AUTO_MIDI_LLM_MODEL=deepseek-v4-flash
AUTO_MIDI_LLM_API_KEY_ENV=10086
```

The key is read at runtime and is never written to `.env`, output files, or
logs. If the gateway is unavailable or returns invalid JSON, generation falls
back to the deterministic local Feel Agent.

Available style constraints:

```text
free
boom_bap
hiphop
trap
minimal
rock
hard_rock
dream_pop
post_rock
psychedelic
jazz
blues
rnb
country
funk
reggae
```

The generator supports `3/4`, `4/4`, and `6/8`. Groove templates are kept
inside the selected style: Rock defaults to `classic_rock`, with optional
`driving_rock`, `half_time_rock`, `sparse_rock`, `shuffle_rock`,
`blues_rock`, `punk_rock`, and `indie_rock`; Reggae defaults to `one_drop`.
Rock templates use explicit Kick/Snare/Hat step patterns while randomness
controls bounded variations and ornament density.

Sections can restrict which drum voices are allowed. Omit `allowed` or use an
empty list to allow all voices:

```json
{
  "name": "intro",
  "bars": 8,
  "allowed": ["crash"],
  "fill": 0,
  "fill_mode": "none"
}
```

`required` means that a voice must occur at least once in the whole section; it
does not force that voice into every bar. Use `voice_placements` when the
location matters:

```json
{
  "name": "outro",
  "bars": 8,
  "groove": "post_rock_release",
  "allowed": ["kick", "snare", "closed_hat", "crash"],
  "required": ["crash"],
  "voice_placements": {"crash": "section_end"},
  "cymbal_role": "closed_hat_quarters",
  "intensity_curve": [
    {"bar": 1, "value": 20},
    {"bar": 8, "value": 5}
  ],
  "density_curve": [
    {"bar": 1, "value": 0.15},
    {"bar": 8, "value": 0.03}
  ]
}
```

Supported voice placements are `auto`, `section_start`, `section_end`,
`first_bar`, `last_bar`, `every_bar`, `phrase_start`, and `phrase_end`.
Supported cymbal roles are `none`, `closed_hat_quarters`,
`closed_hat_eighths`, `open_hat_quarters`, `ride_quarters`, `ride_eighths`, and
`ride_bell_offbeats`. Curves override the linear start/end values.

Presets are style boundaries for generating a new drummer DNA. They are not
fixed drum patterns.

## Concept

The core loop is:

```text
text sections -> NLP TextMap -> generated DrummerDNA -> drum events -> MIDI
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
