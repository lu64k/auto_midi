from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import random
import tempfile

import gradio as gr

from auto_midi.drummer_dna import PRESET_BOUNDS, generate_dna
from auto_midi.drum_execution import (
    build_drum_execution_agent,
    compile_execution_config,
    execution_config_payload,
    validate_execution_routing,
)
from auto_midi.drum_feel import RuleBasedDrumFeelAgent, build_drum_feel_agent, normalize_plan_structure, parse_drum_feels
from auto_midi.groove import default_groove, grooves_for_style
from auto_midi.llm_client import LLMError
from auto_midi.midi_exporter import write_midi
from auto_midi.pattern_generator import generate_events
from auto_midi.sample_kit import inspect_kit
from auto_midi.section_config import load_section_config, parse_section_config
from auto_midi.song_requirements import build_requirements_agent, fallback_song_structure
from auto_midi.song_structure import SECTION_TYPES, apply_song_structure, parse_song_structure, section_configs_from_song_structure
from auto_midi.settings import settings
from auto_midi.style_catalog import catalog_snapshot, groove_owner
from auto_midi.time_signature import SUPPORTED_TIME_SIGNATURES, parse_time_signature
from auto_midi.text_parser import parse_text
from auto_midi.wav_preview import render_preview_wav
from auto_midi.work_history import WorkHistoryStore


ROOT = Path(__file__).resolve().parent
HISTORY_STORE = WorkHistoryStore(ROOT / "data" / "work_history")
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
    options = grooves_for_style(style, include_free=True)
    return gr.Dropdown(choices=list(options), value=default_groove(style))


def _catalog_controls_update(previous_hash: str, style: str, groove: str):
    snapshot = catalog_snapshot()
    if previous_hash == snapshot.content_hash:
        return previous_hash, gr.skip(), gr.skip()
    styles = sorted(snapshot.styles)
    selected_style = style if style in snapshot.styles else "free"
    grooves = grooves_for_style(selected_style, include_free=True)
    selected_groove = groove if groove in grooves else default_groove(selected_style)
    return (
        snapshot.content_hash,
        gr.Dropdown(choices=styles, value=selected_style),
        gr.Dropdown(choices=list(grooves), value=selected_groove),
    )


def _execution_config_payload(configs):
    payload = []
    for config in configs:
        payload.append(
            {
                "name": config.name,
                "type": config.section_type,
                "bars": config.bars,
                "intensity_start": config.intensity_start,
                "intensity_end": config.intensity_end,
                "density_start": config.density_start,
                "density_end": config.density_end,
                "fill": config.fill,
                "fill_mode": config.fill_mode,
                "allowed": list(config.allowed_voices or []),
                "required": list(config.required_voices),
                "voice_placements": config.voice_placements,
                "groove": config.groove,
                "cymbal_role": config.cymbal_role,
                "intensity_curve": [{"bar": bar, "value": value} for bar, value in config.intensity_curve],
                "density_curve": [{"bar": bar, "value": value} for bar, value in config.density_curve],
                "chord_bars": [list(bar) for bar in config.chord_bars],
                "dna_overrides": config.dna_overrides,
            }
        )
    return {"sections": payload}


def _structure_from_inputs(lyrics: str | None, structure_json: str | None):
    if not (structure_json or "").strip():
        raise gr.Error("请先填写歌曲结构 JSON")
    try:
        structure = parse_song_structure(json.loads(structure_json))
        if (lyrics or "").strip():
            text_map = parse_text(lyrics)
            if not text_map.bars:
                raise ValueError("没有解析到有效歌词小节")
            apply_song_structure(text_map, structure)
    except (TypeError, json.JSONDecodeError, ValueError) as exc:
        raise gr.Error(f"歌曲结构 JSON 无效：{exc}") from exc
    return structure


def read_requirements(
    lyrics: str | None,
    bpm: int | float | None,
    time_signature: str,
):
    """Read natural-language requirements and return structure + Feel JSON."""

    print("[read_requirements] start", flush=True)
    if not (lyrics or "").strip():
        raise gr.Error("请先输入歌词")
    if not (lyrics or "").strip() and not (structure_json or "").strip():
        raise gr.Error("请先在歌词框填写歌词和编曲需求")
    try:
        bpm_value = int(bpm)
        seed_value = 0
    except (TypeError, ValueError) as exc:
        raise gr.Error(f"BPM 或 Seed 无效：{exc}") from exc
    if seed_value == -1:
        seed_value = random.randrange(1_000_000_000)
    warnings = []
    # The user textbox is already the complete brief.  Build only a local
    # section scaffold here, then make the single LLM call through Feel Agent.
    requirements_agent = None
    try:
        print("[read_requirements] requirements agent request", flush=True)
        if requirements_agent is None:
            structure = fallback_song_structure(lyrics, lyrics, bpm_value, time_signature)
            warnings.append("需求整理 Agent 未配置，使用本地回退")
        else:
            structure = requirements_agent.generate(
                lyrics,
                lyrics,
                bpm_value,
                time_signature,
                seed_value,
            )
        print("[read_requirements] requirements agent returned", flush=True)
    except (LLMError, ValueError) as exc:
        print(f"[read_requirements] requirements agent failed: {exc}", flush=True)
        structure = fallback_song_structure(lyrics, lyrics, bpm_value, time_signature)
        warnings.append(f"需求整理 Agent 失败，已回退：{exc}")
    # The local scaffold is not an Agent and must not be reported as one.
    warnings = []
    preset_value = settings.preset
    groove_value = settings.groove or default_groove(preset_value)
    # The first button has exactly one LLM call: requirements -> structure.
    # Drum feel is kept local here and can be edited/overridden downstream.
    feel_agent = build_drum_feel_agent()
    raw_plan = None
    try:
        print("[read_requirements] feel agent request", flush=True)
        if hasattr(feel_agent, "generate_raw_plan"):
            raw_plan = feel_agent.generate_raw_plan(
                lyrics,
                bpm_value,
                time_signature,
                preset_value,
                groove_value,
                seed_value,
            )
            try:
                structure = normalize_plan_structure(raw_plan, lyrics)
            except ValueError as exc:
                structure = fallback_song_structure(lyrics, lyrics, bpm_value, time_signature)
                warnings.append(f"Hidden structure fallback: {exc}")
            feels = ()
        else:
            feels = feel_agent.generate(
                structure,
                preset_value,
                groove_value,
                seed_value,
                requirements=lyrics,
            )
        print("[read_requirements] feel agent returned", flush=True)
    except (LLMError, ValueError) as exc:
        print(f"[read_requirements] feel agent failed: {exc}", flush=True)
        raise gr.Error(f"Feel Agent gateway unavailable: {exc}") from exc
        feels = RuleBasedDrumFeelAgent().generate(structure, preset_value, groove_value, seed_value)
        warnings.append(f"Feel Agent 失败，已回退：{exc}")
    structure_payload = {
        "title": structure.title,
        "bpm": structure.bpm,
        "time_signature": structure.time_signature,
        "key": structure.key,
        "sections": [
            {
                "id": section.id,
                "type": section.type,
                "index": section.index,
                "bars": section.bars,
                "lyrics_start": section.lyrics_start,
                "lyrics_end": section.lyrics_end,
                "chords": [list(bar) for bar in section.chord_bars],
                "repeat_of": section.repeat_of,
            }
            for section in structure.sections
        ],
    }
    result = (
        json.dumps(structure_payload, ensure_ascii=False, indent=2),
        json.dumps(
            raw_plan if raw_plan is not None else {"structure": structure_payload, "feels": [feel.to_plan_dict() for feel in feels]},
            ensure_ascii=False,
            indent=2,
        ),
        {
            "stage": "requirements_read",
            "status": "ok",
            "structure_sections": len(structure.sections),
            "feel_source": "llm_raw" if raw_plan is not None else (feels[0].source if feels else "none"),
            "warnings": warnings,
        },
    )
    print("[read_requirements] completed", flush=True)
    return result


def generate_execution_form(
    structure_json: str | None,
    feel_json: str | None,
    preset: str | None,
    groove: str | None,
    seed: int | float | None,
):
    """Run only the second Agent and return editable execution JSON."""

    if (feel_json or "").strip():
        try:
            raw_plan = json.loads(feel_json)
            raw_seed = int(seed) if seed is not None else -1
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise gr.Error(f"First Agent JSON or Seed is invalid: {exc}") from exc
        if isinstance(raw_plan, dict) and ("feels" in raw_plan or "structure" in raw_plan):
            if raw_seed == -1:
                raw_seed = random.randrange(1_000_000_000)
            execution_agent = build_drum_execution_agent()
            if not hasattr(execution_agent, "generate_from_plan_payload"):
                raise gr.Error("Execution Agent is not configured")
            try:
                preset_value = preset if preset in PRESET_BOUNDS else settings.preset
                groove_value = (
                    "free"
                    if groove == "free"
                    else groove if groove in grooves_for_style(preset_value) else default_groove(preset_value)
                )
                routing, configs = execution_agent.generate_execution_plan(
                    raw_plan,
                    raw_seed,
                    preset=preset_value,
                    groove=groove_value,
                )
            except (LLMError, ValueError) as exc:
                raise gr.Error(f"Execution Agent failed: {exc}") from exc
            return json.dumps(execution_config_payload(configs, routing), ensure_ascii=False, indent=2)

    structure = _structure_from_inputs(None, structure_json)
    if not (feel_json or "").strip():
        raise gr.Error("请先点击“读取需求”生成 Drum Feel")
    try:
        feels = parse_drum_feels(json.loads(feel_json), structure)
        seed_value = int(seed) if seed is not None else -1
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise gr.Error(f"Drum Feel JSON 或 Seed 无效：{exc}") from exc
    if seed_value == -1:
        seed_value = random.randrange(1_000_000_000)
    try:
        execution_agent = build_drum_execution_agent()
        configs = execution_agent.generate(structure, feels, seed_value)
    except (LLMError, ValueError):
        configs = compile_execution_config(structure, feels)
    return json.dumps(execution_config_payload(configs), ensure_ascii=False, indent=2)


def _structure_from_execution_config(configs, bpm: int, time_signature: str):
    """Derive hidden generation structure from a standalone execution config."""

    sections = []
    cursor = 1
    for index, config in enumerate(configs, start=1):
        section_type = config.section_type if config.section_type in SECTION_TYPES else "instrumental"
        chord_bars = [list(bar) for bar in config.chord_bars]
        if chord_bars and len(chord_bars) != config.bars:
            chord_bars = [chord_bars[position % len(chord_bars)] for position in range(config.bars)]
        sections.append(
            {
                "id": config.name or f"section_{index}",
                "type": section_type,
                "index": index,
                "bars": config.bars,
                "lyrics_start": cursor,
                "lyrics_end": cursor + config.bars - 1,
                "chords": chord_bars,
                "repeat_of": config.repeat_of,
            }
        )
        cursor += config.bars
    return parse_song_structure(
        {
            "title": "execution_config",
            "bpm": bpm,
            "time_signature": time_signature,
            "sections": sections,
        }
    )


def _resolve_routing_controls(
    section_configs,
    execution_routing,
    ui_preset: str,
    ui_groove: str,
    use_execution_routing: bool,
):
    warning = None
    if use_execution_routing and execution_routing is not None:
        return (
            execution_routing.style,
            execution_routing.global_groove,
            section_configs,
            "execution_config",
            warning,
        )
    if use_execution_routing and execution_routing is None:
        warning = "Execution config has no routing metadata; UI routing was used"
    preset = ui_preset if ui_preset != "free" else execution_routing.style if execution_routing else "free"
    if ui_groove != "free" and groove_owner(ui_groove) == preset:
        groove = ui_groove
        section_configs = tuple(replace(config, groove=groove) for config in section_configs)
    elif execution_routing is not None and execution_routing.style == preset:
        groove = execution_routing.global_groove
    else:
        groove = default_groove(preset)
        section_configs = tuple(replace(config, groove=groove) for config in section_configs)
    return preset, groove, section_configs, "ui", warning


def render_song(
    lyrics: str | None,
    song_structure_json: str | None,
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
    feel_override_json: str | None = None,
    execution_override_json: str | None = None,
    use_execution_routing: bool = False,
):
    standalone_configs = None
    standalone_structure = None
    execution_routing = None
    if (execution_override_json or "").strip():
        try:
            execution_payload = json.loads(execution_override_json)
            standalone_configs = parse_section_config(execution_payload)
            if isinstance(execution_payload, dict) and "routing" in execution_payload:
                execution_routing, standalone_configs = validate_execution_routing(
                    execution_payload, standalone_configs, None, None
                )
            standalone_bpm = int(bpm if bpm is not None else settings.bpm)
            standalone_structure = _structure_from_execution_config(
                standalone_configs,
                standalone_bpm,
                time_signature,
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise gr.Error(f"Execution config is invalid: {exc}") from exc
        section_json = execution_override_json
        if not (lyrics or "").strip():
            lyrics = "\n".join(f"bar {index}" for index in range(1, standalone_structure.total_bars + 1))

    if not (lyrics or "").strip():
        if settings.test_mode:
            lyrics = DEFAULT_TEST_LYRICS
        else:
            raise gr.Error("请先输入歌词；当前程序按非空行生成小节，空行用于分段。")
    text_map = parse_text(lyrics)
    if not text_map.bars:
        raise gr.Error("no lyric bars were parsed")
    structure = standalone_structure
    agent_feels = None
    agent_execution = None
    if standalone_structure is not None:
        text_map = apply_song_structure(text_map, standalone_structure)
    elif (song_structure_json or "").strip():
        try:
            structure = parse_song_structure(json.loads(song_structure_json))
            text_map = apply_song_structure(text_map, structure)
            section_json = json.dumps(
                {
                    "sections": [
                        {
                            "name": section.id,
                            "type": section.type,
                            "bars": section.bars,
                            "chord_bars": [list(bar) for bar in section.chord_bars],
                            "repeat_of": section.repeat_of,
                        }
                        for section in structure.sections
                    ]
                },
                ensure_ascii=False,
            )
        except (TypeError, json.JSONDecodeError, ValueError) as exc:
            raise gr.Error(f"歌曲结构 JSON 无效：{exc}") from exc
    section_json = section_json or DEFAULT_SECTION_CONFIG
    try:
        json.loads(section_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise gr.Error(f"段落 JSON 无法解析：{exc}") from exc

    # text_map was parsed before applying the user-authored structure.
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
        bpm_value = int(structure.bpm if structure else bpm)
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
    ui_preset_value = preset if preset in PRESET_BOUNDS else settings.preset
    ui_groove_value = str(groove or "free")
    preset_value = ui_preset_value
    groove_value = (
        ui_groove_value
        if ui_groove_value != "free" and groove_owner(ui_groove_value) == preset_value
        else default_groove(preset_value)
    )
    summary_warning = None
    if structure:
        if (execution_override_json or "").strip() or (feel_override_json or "").strip():
            agent_feels = None
        else:
            agent = build_drum_feel_agent()
            try:
                agent_feels = agent.generate(
                    structure,
                    preset=preset_value,
                    groove=groove_value,
                    seed=seed_value,
                )
            except (LLMError, ValueError) as exc:
                agent_feels = RuleBasedDrumFeelAgent().generate(
                    structure,
                    preset=preset_value,
                    groove=groove_value,
                    seed=seed_value,
                )
                summary_warning = f"LLM Agent 调用失败，已回退规则 Agent：{exc}"
        if (feel_override_json or "").strip() and not (execution_override_json or "").strip():
            try:
                agent_feels = parse_drum_feels(json.loads(feel_override_json), structure)
            except (TypeError, json.JSONDecodeError, ValueError) as exc:
                raise gr.Error(f"段落鼓点感觉 JSON 无效：{exc}") from exc
        if (execution_override_json or "").strip():
            agent_execution = ()
        else:
            execution_agent = build_drum_execution_agent()
            try:
                agent_execution = execution_agent.generate(structure, agent_feels, seed_value)
            except (LLMError, ValueError) as exc:
                agent_execution = compile_execution_config(structure, agent_feels)
                summary_warning = (
                    f"{summary_warning}; " if summary_warning else ""
                ) + f"执行配置 LLM 调用失败，已回退本地编译器：{exc}"
        section_configs = agent_execution
        if (execution_override_json or "").strip():
            try:
                json.loads(execution_override_json)
            except (TypeError, json.JSONDecodeError) as exc:
                raise gr.Error(f"最终鼓执行配置 JSON 无法解析：{exc}") from exc
            with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as override_file:
                override_file.write(execution_override_json)
                override_path = Path(override_file.name)
            try:
                section_configs = load_section_config(override_path)
            except (OSError, TypeError, ValueError) as exc:
                raise gr.Error(f"最终鼓执行配置无效：{exc}") from exc
            finally:
                override_path.unlink(missing_ok=True)
            if len(section_configs) != len(structure.sections):
                raise gr.Error(
                    f"最终鼓执行配置包含 {len(section_configs)} 段，"
                    f"但歌曲结构包含 {len(structure.sections)} 段"
                )
            agent_execution = section_configs

    preset_value, groove_value, section_configs, routing_authority, routing_warning = _resolve_routing_controls(
        section_configs,
        execution_routing,
        ui_preset_value,
        ui_groove_value,
        bool(use_execution_routing),
    )
    if routing_warning:
        summary_warning = (f"{summary_warning}; " if summary_warning else "") + routing_warning
    try:
        signature = parse_time_signature(structure.time_signature if structure else time_signature)
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
        "routing_authority": routing_authority,
        "time_signature": str(signature),
        "seed": seed_value,
        "midi": str(midi_path),
    }
    if structure:
        summary["song_structure"] = structure.title
        summary["key"] = structure.key
        summary["agent"] = agent_feels[0].source if agent_feels else "manual"
    if execution_routing is not None:
        summary["routed_style"] = execution_routing.style
        summary["routed_global_groove"] = execution_routing.global_groove
        summary["catalog_version"] = execution_routing.catalog_version
    if summary_warning:
        summary["warning"] = summary_warning
    if not kit_status.ready:
        summary["warning"] = f"测试模式跳过 WAV：样本包缺少 {', '.join(kit_status.missing)}"
    return (
        str(wav_path) if kit_status.ready else None,
        str(midi_path),
        summary,
        json.dumps([feel.to_plan_dict() for feel in agent_feels], ensure_ascii=False, indent=2)
        if agent_feels
        else feel_override_json,
        json.dumps(_execution_config_payload(agent_execution), ensure_ascii=False, indent=2)
        if agent_execution
        else section_json,
    )


def _build_demo_legacy() -> gr.Blocks:
    with gr.Blocks(title="Auto MIDI - Drum DNA") as demo:
        gr.Markdown("输入歌词生成鼓组 WAV 和 MIDI。测试模式下歌词为空时使用固定测试文本。")
        with gr.Row():
            with gr.Column(scale=1):
                lyrics = gr.Textbox(
                    label="歌词 / 自然语言需求",
                    lines=18,
                    value=DEFAULT_TEST_LYRICS if settings.test_mode else None,
                    placeholder="输入歌词，并在其中写入段落、和弦、鼓点和编曲需求；第一步 Agent 会统一读取。",
                )
                song_structure_json = gr.Code(visible=False,
                    label="歌曲结构 JSON（第一步输出，可编辑）",
                    language="json",
                    value="",
                    lines=18,
                )
                section_json = gr.Code(visible=False,
                    label="最终段落执行配置 JSON",
                    language="json",
                    value=DEFAULT_SECTION_CONFIG,
                    lines=22,
                )
                read_requirements_button = gr.Button("1. 读取需求（Feel Agent）")
                compile_execution_button = gr.Button("2. 生成执行表（Execution Agent）")
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
                generate = gr.Button("3. 生成鼓点", variant="primary")

        with gr.Row():
            audio = gr.Audio(label="WAV 预览", type="filepath")
            midi = gr.File(label="MIDI 下载")
        summary = gr.JSON(label="生成摘要")
        feel_output = gr.Code(label="段落鼓点感觉 Agent 输出（可编辑）", language="json", lines=18)
        execution_output = gr.Code(label="最终鼓执行配置", language="json", lines=18)
        read_requirements_button.click(
            fn=read_requirements,
            inputs=[lyrics, bpm, time_signature],
            outputs=[song_structure_json, feel_output, summary],
            concurrency_limit=1,
        )
        compile_execution_button.click(
            fn=generate_execution_form,
            inputs=[song_structure_json, feel_output, preset, groove, seed],
            outputs=[execution_output],
        )
        generate.click(
            fn=render_song,
            inputs=[lyrics, song_structure_json, section_json, bpm, complexity, intensity, fill, randomness, preset, groove, time_signature, seed, sample_kit, feel_output, execution_output],
            outputs=[audio, midi, summary, feel_output, execution_output],
        )
        preset.change(fn=_groove_dropdown_update, inputs=preset, outputs=groove)
    return demo


def _history_dropdown(value: str | None = None):
    return gr.Dropdown(choices=HISTORY_STORE.titles(), value=value)


def _save_active_work(
    active_title: str | None,
    entered_title: str | None,
    lyrics: str | None,
    feel_json: str | None,
    execution_json: str | None,
):
    record = HISTORY_STORE.save(
        active_title or entered_title,
        lyrics,
        feel_json,
        execution_json,
    )
    return (
        record.title,
        record.title,
        _history_dropdown(record.title),
        f"已保存：{record.title}（{record.updated_at}）",
    )


def _resolve_work_title(
    entered_title: str | None,
    active_title: str | None,
    lyrics: str | None,
    feel_json: str | None,
    execution_json: str | None,
):
    target = str(entered_title or "").strip()
    active = str(active_title or "").strip()
    if active and active.casefold() != target.casefold():
        HISTORY_STORE.save(active, lyrics, feel_json, execution_json)
    existing = HISTORY_STORE.load(target)
    if existing is not None:
        return (
            existing.title,
            existing.title,
            _history_dropdown(existing.title),
            existing.lyrics_and_requirements,
            existing.feel_plan_json,
            existing.execution_config_json,
            f"已读取：{existing.title}",
        )
    record = HISTORY_STORE.save(target, lyrics, feel_json, execution_json)
    return (
        record.title,
        record.title,
        _history_dropdown(record.title),
        record.lyrics_and_requirements,
        record.feel_plan_json,
        record.execution_config_json,
        f"已新建：{record.title}",
    )


def _load_history_work(
    selected_title: str | None,
    active_title: str | None,
    entered_title: str | None,
    lyrics: str | None,
    feel_json: str | None,
    execution_json: str | None,
):
    active = str(active_title or entered_title or "").strip()
    selected = str(selected_title or "").strip()
    if active and selected and active.casefold() != selected.casefold():
        HISTORY_STORE.save(active, lyrics, feel_json, execution_json)
    record = HISTORY_STORE.load(selected)
    if record is None:
        return (
            active_title,
            entered_title,
            _history_dropdown(active or None),
            lyrics,
            feel_json,
            execution_json,
            "未找到所选历史记录",
        )
    return (
        record.title,
        record.title,
        _history_dropdown(record.title),
        record.lyrics_and_requirements,
        record.feel_plan_json,
        record.execution_config_json,
        f"已读取：{record.title}",
    )


def build_demo() -> gr.Blocks:
    """Build the compact three-tab Gradio interface."""

    with gr.Blocks(title="Auto MIDI - Drum DNA") as demo:
        gr.Markdown("输入歌词和自然语言编曲需求，依次生成 Feel 计划、执行配置和鼓点。")

        active_title = gr.State(value="")
        with gr.Row():
            work_title = gr.Textbox(
                label="作品标题",
                placeholder="留空时自动使用日期命名",
                scale=1,
            )
            history_dropdown = gr.Dropdown(
                label="历史作品",
                choices=HISTORY_STORE.titles(),
                value=None,
                scale=1,
            )
        history_status = gr.Markdown("尚未保存")

        lyrics = gr.Textbox(
            label="歌词 / 自然语言需求",
            lines=16,
            value=DEFAULT_TEST_LYRICS if settings.test_mode else None,
            placeholder="输入歌词、段落、小节数、和弦及鼓点要求。",
        )
        song_structure_json = gr.State(value="")
        section_json = gr.State(value=DEFAULT_SECTION_CONFIG)

        with gr.Row():
            read_requirements_button = gr.Button("1. 生成 Feel 计划")
            compile_execution_button = gr.Button("2. 生成执行配置")
            generate = gr.Button("3. 生成鼓点", variant="primary")

        with gr.Tabs():
            with gr.Tab("Feel 计划"):
                feel_output = gr.Code(
                    label="段落鼓点 Feel（可编辑）",
                    language="json",
                    lines=24,
                )
            with gr.Tab("执行配置"):
                execution_output = gr.Code(
                    label="最终鼓执行配置（可编辑）",
                    language="json",
                    lines=24,
                )
            with gr.Tab("风格预设"):
                with gr.Row():
                    preset = gr.Dropdown(
                        label="风格预设",
                        choices=sorted(PRESET_BOUNDS),
                        value=settings.preset,
                    )
                    groove = gr.Dropdown(
                        label="节奏型",
                        choices=grooves_for_style(settings.preset, include_free=True),
                        value=settings.groove or default_groove(settings.preset),
                    )
                    use_execution_routing = gr.Checkbox(
                        label="使用执行配置中的风格与节奏型",
                        value=False,
                    )
                with gr.Row():
                    time_signature = gr.Dropdown(
                        label="拍号",
                        choices=list(SUPPORTED_TIME_SIGNATURES),
                        value=settings.time_signature,
                    )
                    bpm = gr.Slider(30, 260, value=settings.bpm, step=1, label="BPM")
                    seed = gr.Number(value=7, precision=0, label="Seed（-1 为随机）")
                with gr.Row():
                    complexity = gr.Slider(0, 100, value=settings.complexity, step=1, label="整体复杂度")
                    intensity = gr.Slider(0, 100, value=settings.intensity, step=1, label="整体强度")
                with gr.Row():
                    fill = gr.Slider(0, 100, value=settings.fill, step=1, label="整体 Fill")
                    randomness = gr.Slider(0, 100, value=settings.randomness, step=1, label="整体随机性")
                sample_kit = gr.Textbox(label="样本包目录", value=str(DEFAULT_KIT))

        catalog_hash = gr.State(value=catalog_snapshot().content_hash)
        catalog_timer = gr.Timer(value=5.0)

        with gr.Row():
            audio = gr.Audio(label="WAV 预览", type="filepath")
            midi = gr.File(label="MIDI 下载")
        summary = gr.JSON(label="处理摘要")

        history_load_outputs = [
            active_title,
            work_title,
            history_dropdown,
            lyrics,
            feel_output,
            execution_output,
            history_status,
        ]
        title_inputs = [work_title, active_title, lyrics, feel_output, execution_output]
        work_title.submit(
            fn=_resolve_work_title,
            inputs=title_inputs,
            outputs=history_load_outputs,
            concurrency_limit=1,
        )
        work_title.blur(
            fn=_resolve_work_title,
            inputs=title_inputs,
            outputs=history_load_outputs,
            concurrency_limit=1,
        )
        history_dropdown.change(
            fn=_load_history_work,
            inputs=[history_dropdown, active_title, work_title, lyrics, feel_output, execution_output],
            outputs=history_load_outputs,
            concurrency_limit=1,
        )

        save_inputs = [active_title, work_title, lyrics, feel_output, execution_output]
        save_outputs = [active_title, work_title, history_dropdown, history_status]
        lyrics.blur(fn=_save_active_work, inputs=save_inputs, outputs=save_outputs, concurrency_limit=1)
        feel_output.change(fn=_save_active_work, inputs=save_inputs, outputs=save_outputs, concurrency_limit=1)
        execution_output.change(fn=_save_active_work, inputs=save_inputs, outputs=save_outputs, concurrency_limit=1)

        read_event = read_requirements_button.click(
            fn=read_requirements,
            inputs=[lyrics, bpm, time_signature],
            outputs=[song_structure_json, feel_output, summary],
            concurrency_limit=1,
        )
        read_event.then(fn=_save_active_work, inputs=save_inputs, outputs=save_outputs, concurrency_limit=1)

        execution_event = compile_execution_button.click(
            fn=generate_execution_form,
            inputs=[song_structure_json, feel_output, preset, groove, seed],
            outputs=[execution_output],
            concurrency_limit=1,
        )
        execution_event.then(fn=_save_active_work, inputs=save_inputs, outputs=save_outputs, concurrency_limit=1)

        save_before_generate = generate.click(
            fn=_save_active_work,
            inputs=save_inputs,
            outputs=save_outputs,
            concurrency_limit=1,
        )
        save_before_generate.then(
            fn=render_song,
            inputs=[
                lyrics,
                song_structure_json,
                section_json,
                bpm,
                complexity,
                intensity,
                fill,
                randomness,
                preset,
                groove,
                time_signature,
                seed,
                sample_kit,
                feel_output,
                execution_output,
                use_execution_routing,
            ],
            outputs=[audio, midi, summary, feel_output, execution_output],
            concurrency_limit=1,
        )
        preset.change(fn=_groove_dropdown_update, inputs=preset, outputs=groove)
        catalog_timer.tick(
            fn=_catalog_controls_update,
            inputs=[catalog_hash, preset, groove],
            outputs=[catalog_hash, preset, groove],
            concurrency_limit=1,
        )
    return demo


if __name__ == "__main__":
    build_demo().launch(
        server_name=settings.gradio_server_name,
        server_port=settings.gradio_server_port,
        share=settings.gradio_share,
    )
