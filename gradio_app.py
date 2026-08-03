from __future__ import annotations

import json
from pathlib import Path
import random
import tempfile

import gradio as gr

from auto_midi.drummer_dna import PRESET_BOUNDS, generate_dna
from auto_midi.midi_exporter import write_midi
from auto_midi.pattern_generator import generate_events
from auto_midi.sample_kit import inspect_kit
from auto_midi.section_config import load_section_config
from auto_midi.text_parser import parse_text
from auto_midi.wav_preview import render_preview_wav


ROOT = Path(__file__).resolve().parent
DEFAULT_KIT = ROOT / "samples" / "classic_kit"
DEFAULT_SECTION_CONFIG = (ROOT / "test" / "example1" / "drum_section_config.json").read_text(encoding="utf-8")


def render_song(
    lyrics: str,
    section_json: str,
    bpm: int,
    complexity: int,
    intensity: int,
    fill: int,
    randomness: int,
    preset: str,
    seed: int,
    sample_kit: str,
):
    if not lyrics.strip():
        raise gr.Error("请先输入歌词；当前程序按非空行生成小节，空行用于分段。")
    try:
        json.loads(section_json)
    except json.JSONDecodeError as exc:
        raise gr.Error(f"段落 JSON 无法解析：{exc}") from exc

    text_map = parse_text(lyrics)
    if not text_map.bars:
        raise gr.Error("没有解析到有效歌词小节。")

    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as config_file:
        config_file.write(section_json)
        config_path = Path(config_file.name)
    try:
        section_configs = load_section_config(config_path)
    except (OSError, TypeError, ValueError) as exc:
        raise gr.Error(f"段落配置无效：{exc}") from exc
    finally:
        config_path.unlink(missing_ok=True)

    if len(section_configs) != text_map.section_count:
        raise gr.Error(
            f"段落数量不一致：歌词解析出 {text_map.section_count} 段，"
            f"配置中有 {len(section_configs)} 段。"
        )

    seed_value = int(seed)
    dna = generate_dna(
        text_map=text_map,
        rng=random.Random(seed_value),
        complexity=int(complexity),
        intensity=int(intensity),
        fill=int(fill),
        randomness=int(randomness),
        preset=preset,
    )
    try:
        events = generate_events(
            text_map,
            dna,
            random.Random(seed_value),
            intensity=int(intensity),
            fill=int(fill),
            section_configs=section_configs,
        )
    except ValueError as exc:
        raise gr.Error(f"段落配置与歌词小节不匹配：{exc}") from exc

    kit_status = inspect_kit(Path(sample_kit).expanduser())
    if not kit_status.ready:
        raise gr.Error(f"样本包缺少：{', '.join(kit_status.missing)}")

    output_dir = ROOT / "outputs" / "gradio"
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"take_{seed_value}"
    midi_path = output_dir / f"{stem}.mid"
    wav_path = output_dir / f"{stem}.wav"
    write_midi(events, midi_path, bpm=int(bpm))
    render_preview_wav(events, kit_status, wav_path, bpm=int(bpm), bar_count=len(text_map.bars))

    return str(wav_path), str(midi_path), {
        "bars": len(text_map.bars),
        "sections": text_map.section_count,
        "events": len(events),
        "preset": dna.style,
        "seed": seed_value,
        "midi": str(midi_path),
    }


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="Auto MIDI · Drum DNA") as demo:
        gr.Markdown(
            """# Auto MIDI · Drum DNA

输入最终段落配置后生成一段鼓组 WAV 和 MIDI。当前规则：每个非空歌词行对应一个小节，空行分段。"""
        )
        with gr.Row():
            with gr.Column(scale=1):
                lyrics = gr.Textbox(
                    label="歌词 / 小节文本",
                    lines=18,
                    placeholder="每个非空行对应一个小节；空行用于段落分隔。",
                )
                section_json = gr.Code(
                    label="最终段落执行配置 JSON",
                    language="json",
                    value=DEFAULT_SECTION_CONFIG,
                    lines=22,
                )
            with gr.Column(scale=1):
                preset = gr.Dropdown(label="现有风格预设", choices=sorted(PRESET_BOUNDS), value="minimal")
                with gr.Row():
                    bpm = gr.Slider(30, 260, value=92, step=1, label="BPM")
                    seed = gr.Number(value=7, precision=0, label="Seed")
                complexity = gr.Slider(0, 100, value=55, step=1, label="全局复杂度")
                intensity = gr.Slider(0, 100, value=65, step=1, label="全局强度")
                fill = gr.Slider(0, 100, value=35, step=1, label="全局 Fill")
                randomness = gr.Slider(0, 100, value=45, step=1, label="全局随机性")
                sample_kit = gr.Textbox(label="样本包目录", value=str(DEFAULT_KIT))
                generate = gr.Button("生成鼓组", variant="primary")

        with gr.Row():
            audio = gr.Audio(label="WAV 预览", type="filepath")
            midi = gr.File(label="MIDI 下载")
        summary = gr.JSON(label="生成摘要")

        generate.click(
            fn=render_song,
            inputs=[lyrics, section_json, bpm, complexity, intensity, fill, randomness, preset, seed, sample_kit],
            outputs=[audio, midi, summary],
        )
    return demo


if __name__ == "__main__":
    build_demo().launch(server_name="0.0.0.0", server_port=8006)
