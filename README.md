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

## Gradio 工作流

### 启动

Windows PowerShell：

```powershell
& .\.venv\Scripts\python.exe .\gradio_app.py
```

默认地址为 `http://127.0.0.1:8006`。端口由 `.env` 中的
`GRADIO_SERVER_PORT` 控制；如果 8006 已被占用，请结束旧进程或临时改用
其他端口。

### 页面流程

页面只有一份“歌词 / 自然语言需求”输入。歌词、段落名称、小节数、段落和弦、
编曲方向以及鼓点要求都写在这里，不需要预先整理 JSON。例如：

```text
作品偏经典摇滚，120 BPM，4/4。
Intro 4 小节，只要 crash 和少量军鼓。
Verse 1 16 小节，和弦 C/G-E-A-Fm，鼓点克制。
Chorus 8 小节，保持同一基础节奏型，但增加力度和开镲。

[Verse 1]
歌词……
```

推荐按以下三步操作：

```text
歌词与自然语言需求
        │
        ▼
1. 生成 Feel 计划（第一 Agent）
        │  分析全曲段落、每段小节/和弦、鼓点感觉及前后关系
        ▼
可编辑的 Feel JSON
        │
        ▼
2. 生成执行配置（第二 Agent + groove 路由 Skill）
        │  选择风格与节奏型，并转换为程序可执行参数
        ▼
可编辑的执行配置 JSON
        │
        ▼
3. 生成鼓点
        └─ MIDI + WAV 预览 + 处理摘要
```

#### 1. 生成 Feel 计划

第一 Agent 读取完整输入，一次性给出所有段落的 Feel 计划。它的重点是描述每段
鼓点的角色、起伏、密度、动态以及与上一段/下一段的关系，而不是过早决定所有
程序数值。段落和弦只属于对应段落；未提供和弦时可以留空。

输出显示在“Feel 计划”页签，可以人工修改。这个 JSON 的主要接收者是第二
Agent，因此允许保留有表达力的自然语言描述。

#### 2. 生成执行配置

第二 Agent 把 Feel 计划转换为程序能够直接读取的段落配置，包括强度、密度、
Fill、鼓件限制、鼓件位置、动态曲线以及 groove。它同时调用项目内的路由 Skill，
处理两层选择：

- `style`：全曲鼓手/DNA 的大风格，例如 `rock`、`dream_pop`；
- `groove`：该风格内的具体节奏骨架，例如 `classic_rock`、`sparse_dream`。

风格或节奏型选择 `free` 时由 Agent 判断。路由默认先为全曲选择一个 groove，
不会为了制造变化而给每个段落随意换节奏型。普通的主歌/副歌能量差异通过力度、
密度、Fill 和镲片变化表达；只有明确的 half-time、shuffle、one-drop 等骨架变化
才允许切换 section groove。

输出显示在“执行配置”页签，也可以手工编辑。`allowed=[]` 或空值表示该段允许
使用全部鼓件；`required` 只表示该鼓件在整段内必须至少出现一次。

#### 3. 生成鼓点

第三步读取“执行配置”中的合法 JSON，生成 MIDI 和 WAV。只要这个框里已有合法
执行配置，就可以直接生成，不要求本次页面会话必须先执行第一、第二按钮。因此，
历史配置或手工编写的配置也能直接运行。

“风格预设”页签中的“使用执行配置中的风格与节奏型”决定最终控制权：

- 勾选：以执行配置 JSON 中的 `routing.style`、`routing.global_groove` 和各段
  `groove` 为准；
- 不勾选：以当前 UI 的风格和节奏型为准；固定 groove 会覆盖所有段落；
- UI groove 为 `free`：接受执行配置中已经解析出的 Agent 路由结果。

拍号、BPM、Seed、整体复杂度、强度、Fill、随机性和样本包目录也在这个页签设置。
`Seed=-1` 表示每次随机生成实际 Seed；固定整数可复现同一 take。

### 历史记录

顶部“作品标题”和“历史作品”用于保存工作状态：

- 输入一个新标题会创建记录；
- 输入与历史记录相同的标题会读取该记录，后续修改原位覆盖；
- 标题留空时以当天日期自动命名，重名时追加序号；
- 保存内容包括原始歌词/需求、Feel JSON 和执行配置 JSON；
- 编辑内容、运行 Agent 或生成鼓点时会自动保存。

### 风格目录热更新

`auto_midi/catalog/drum_styles.json` 是 UI 选项、路由 Skill、DNA 边界、groove
profile 和显式 step pattern 的统一数据源。Gradio 每五秒检查一次文件：增加或
调整风格/groove 后无须重启服务；如果新文件校验失败，程序继续使用上一份有效
目录并输出警告。

### Internal LLM gateway

When the system environment variable `10086` is available, the Gradio structure
mode uses the configured OpenAI-compatible gateway for Drum Feel generation:

```text
AUTO_MIDI_LLM_BASE_URL=http://gpus.pixo.local:10086/v1
AUTO_MIDI_LLM_MODEL=deepseek-v4-flash
AUTO_MIDI_LLM_API_KEY_ENV=10086
```

The key is read at runtime and is never written to `.env`, output files, or
logs. If the gateway is unavailable or returns invalid JSON, the corresponding
Agent button reports the gateway/validation error; it does not silently replace
the requested LLM result with an unrelated local plan.

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
