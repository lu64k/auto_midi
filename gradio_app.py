from __future__ import annotations

import json
from pathlib import Path
import random
import tempfile

import gradio as gr

from auto_midi.drummer_dna import PRESET_BOUNDS, generate_dna
from auto_midi.groove import default_groove, grooves_for_style
from auto_midi.midi_exporter import write_midi
from auto_midi.pattern_generator import generate_events
from auto_midi.sample_kit import inspect_kit
from auto_midi.section_config import load_section_config
from auto_midi.settings import settings
from auto_midi.time_signature import SUPPORTED_TIME_SIGNATURES, parse_time_signature
from auto_midi.text_parser import parse_text
from auto_midi.wav_preview import render_preview_wav


ROOT = Path(__file__).resolve().parent
DEFAULT_KIT = settings.sample_kit
DEFAULT_SECTION_CONFIG = (ROOT / "test" / "example1" / "drum_section_config.json").read_text(encoding="utf-8")


def _build_default_test_lyrics() -> str:
    """Create deterministic placeholder bars matching the fixed test config."""
    payload = json.loads(DEFAULT_SECTION_CONFIG)
    sections = []
    for section_index, section in enumerate(payload["sections"], start=1):
        bars = int(section["bars"])
        sections.append("\n".join(f"test section {section_index} bar {bar}" for bar in range(1, bars + 1)))
    return "\n\n".join(sections)


DEFAULT_TEST_LYRICS = _build_default_test_lyrics()


def _groove_dropdown_update(style: str):
    options = grooves_for_style(style)
    return gr.Dropdown(choices=list(options), value=default_groove(style))


def render_song(
    lyrics: str | None,
    section_json: str | None,
    bpm: int | float | None,
    complexity: int | float | None,
    intensity: int | float | None,
    fill: int | float | None,
    randomness: int | float | None,
    preset: str | None,
    groove: str | None,
    time_signature: str,
    seed: int | float | None,
    sample_kit: str | None,
):
    if not (lyrics or "").strip():
        if settings.test_mode:
            lyrics = DEFAULT_TEST_LYRICS
        else:
            raise gr.Error("请先输入歌词；当前程序按非空行生成小节，空行用于分段。")
    section_json = section_json or DEFAULT_SECTION_CONFIG
    try:
        json.loads(section_json)
    except (TypeError, json.JSONDecodeError) as exc:
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

    try:
        requested_seed = int(seed) if seed is not None else -1
        seed_value = random.randrange(1_000_000_000) if requested_seed == -1 else requested_seed
        bpm_value = int(bpm)
        complexity_value = int(complexity)
        intensity_value = int(intensity)
        fill_value = int(fill)
        randomness_value = int(randomness)
    except (TypeError, ValueError) as exc:
        raise gr.Error(f"数值参数无效：{exc}") from exc

    if not 30 <= bpm_value <= 260:
        raise gr.Error("BPM 必须在 30 到 260 之间。")
    if any(value < 0 or value > 100 for value in (complexity_value, intensity_value, fill_value, randomness_value)):
        raise gr.Error("复杂度、强度、Fill 和随机性必须在 0 到 100 之间。")
    preset_value = preset if preset in PRESET_BOUNDS else settings.preset
    groove_value = groove if groove in grooves_for_style(preset_value) else default_groove(preset_value)
    try:
        signature = parse_time_signature(time_signature)
    except ValueError as exc:
        raise gr.Error(str(exc)) from exc

    dna = generate_dna(
        text_map=text_map,
        rng=random.Random(seed_value),
        complexity=complexity_value,
        intensity=intensity_value,
        fill=fill_value,
        randomness=randomness_value,
        preset=preset_value,
        groove=groove_value,
    )
    try:
        events = generate_events(
            text_map,
            dna,
            random.Random(seed_value),
            intensity=intensity_value,
            fill=fill_value,
            section_configs=section_configs,
            time_signature=signature,
        )
    except ValueError as exc:
        raise gr.Error(f"段落配置与歌词小节不匹配：{exc}") from exc

    kit_status = inspect_kit(Path(sample_kit or DEFAULT_KIT).expanduser())
    output_dir = settings.output_dir / "gradio"
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"take_{seed_value}"
    midi_path = output_dir / f"{stem}.mid"
    wav_path = output_dir / f"{stem}.wav"
    try:
        write_midi(events, midi_path, bpm=bpm_value, time_signature=signature)
        if kit_status.ready:
            render_preview_wav(
                events,
                kit_status,
                wav_path,
                bpm=bpm_value,
                bar_count=len(text_map.bars),
                time_signature=signature,
            )
        elif not settings.test_mode:
            raise FileNotFoundError(f"样本包缺少：{', '.join(kit_status.missing)}")
    except (OSError, ValueError, FileNotFoundError) as exc:
        raise gr.Error(f"输出文件生成失败：{exc}") from exc

    summary = {
        "bars": len(text_map.bars),
        "sections": text_map.section_count,
        "events": len(events),
        "preset": dna.style,
        "groove": groove_value,
        "time_signature": str(signature),
        "seed": seed_value,
        "midi": str(midi_path),
    }
    if not kit_status.ready:
        summary["warning"] = f"测试模式跳过 WAV：样本包缺少 {', '.join(kit_status.missing)}"
    return (str(wav_path) if kit_status.ready else None), str(midi_path), summary


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="Auto MIDI - Drum DNA") as demo:
        gr.Markdown("输入歌词生成鼓组 WAV 和 MIDI。测试模式下歌词为空时使用固定测试文本。")
        with gr.Row():
            with gr.Column(scale=1):
                lyrics = gr.Textbox(
                    label="歌词 / 小节文本",
                    lines=18,
                    value=DEFAULT_TEST_LYRICS if settings.test_mode else None,
                    placeholder="每个非空行对应一个小节；空行用于段落分隔。",
                )
                section_json = gr.Code(
                    label="最终段落执行配置 JSON",
                    language="json",
                    value=DEFAULT_SECTION_CONFIG,
                    lines=22,
                )
            with gr.Column(scale=1):
                preset = gr.Dropdown(label="风格预设", choices=sorted(PRESET_BOUNDS), value=settings.preset)
                groove = gr.Dropdown(
                    label="节奏型",
                    choices=grooves_for_style(settings.preset),
                    value=settings.groove or default_groove(settings.preset),
                )
                with gr.Row():
                    time_signature = gr.Dropdown(
                        label="拍号",
                        choices=list(SUPPORTED_TIME_SIGNATURES),
                        value=settings.time_signature,
                    )
                    bpm = gr.Slider(30, 260, value=settings.bpm, step=1, label="BPM")
                    seed = gr.Number(value=7, precision=0, label="Seed（-1 = 随机）")
                complexity = gr.Slider(0, 100, value=settings.complexity, step=1, label="整体复杂度")
                intensity = gr.Slider(0, 100, value=settings.intensity, step=1, label="整体强度")
                fill = gr.Slider(0, 100, value=settings.fill, step=1, label="整体 Fill")
                randomness = gr.Slider(0, 100, value=settings.randomness, step=1, label="整体随机性")
                sample_kit = gr.Textbox(label="样本包目录", value=str(DEFAULT_KIT))
                generate = gr.Button("生成鼓组", variant="primary")

        with gr.Row():
            audio = gr.Audio(label="WAV 预览", type="filepath")
            midi = gr.File(label="MIDI 下载")
        summary = gr.JSON(label="生成摘要")
        generate.click(
            fn=render_song,
            inputs=[lyrics, section_json, bpm, complexity, intensity, fill, randomness, preset, groove, time_signature, seed, sample_kit],
            outputs=[audio, midi, summary],
        )
        preset.change(fn=_groove_dropdown_update, inputs=preset, outputs=groove)
    return demo


if __name__ == "__main__":
    build_demo().launch(
        server_name=settings.gradio_server_name,
        server_port=settings.gradio_server_port,
        share=settings.gradio_share,
    )
