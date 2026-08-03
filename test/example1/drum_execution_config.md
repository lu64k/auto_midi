# Example 1：鼓机执行配置表

> 这是程序侧的规划版配置。字段名和参数范围需要与现有 `drum dna` 实现核对后再正式确定。

## 全局配置

```text
song_id: example_01

global:
  time_signature: inherit_default
  bpm: inherit_default
  drummer_style: relaxed_groove
  global_humanize: 0.35
  global_swing: 0.10
  global_pattern_variation: 0.25
  global_fill_frequency: 0.15
```

## 段落执行参数

### Intro 01

```text
id: intro_01
type: intro
bars: 8
intensity: 0.10 -> 0.25
pattern_density: 0.05 -> 0.20
kick_activity: 0.10
snare_activity: 0.05
hihat_density: 0.12
ghost_note_amount: 0.00
fill_frequency: 0.00
pattern_variation: 0.10
dropout_probability: 0.20
transition_out: light_pickup
```

### Verse 01

```text
id: verse_01
type: verse
index: 1
bars: 16
intensity: 0.25 -> 0.35
pattern_density: 0.25 -> 0.38
kick_activity: 0.28
snare_activity: 0.42
hihat_density: 0.32
ghost_note_amount: 0.10
fill_frequency: 0.10
pattern_variation: 0.18
dropout_probability: 0.08
transition_in: sparse_entry
transition_out: gentle_build
```

### Chorus 01

```text
id: chorus_01
type: chorus
index: 1
bars: 16
intensity: 0.50 -> 0.65
pattern_density: 0.52 -> 0.65
kick_activity: 0.55
snare_activity: 0.68
hihat_density: 0.55
ghost_note_amount: 0.18
fill_frequency: 0.25
pattern_variation: 0.28
dropout_probability: 0.03
crash_activity: 0.30
transition_in: clear_entry
transition_out: soft_release
```

### Outro 01

```text
id: outro_01
type: outro
bars: 16
intensity: 0.45 -> 0.10
pattern_density: 0.50 -> 0.05
kick_activity: 0.45 -> 0.05
snare_activity: 0.55 -> 0.05
hihat_density: 0.45 -> 0.08
ghost_note_amount: 0.08
fill_frequency: 0.05
pattern_variation: 0.12
dropout_probability: 0.10 -> 0.65
transition_out: fade_or_stop
```

## 当前待核对项

- `drummer_style` 的实际预设名称
- `global_humanize`、`global_swing` 是否已有对应参数
- `kick_activity`、`snare_activity`、`hihat_density` 的实际字段名称
- `transition_in`、`transition_out` 是否由程序支持
- 强度和密度是否使用 `0.0～1.0`，或需要映射到其他范围
- 参数曲线是否支持 `start -> end`
