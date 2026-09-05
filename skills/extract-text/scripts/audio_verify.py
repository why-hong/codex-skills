#!/usr/bin/env python3
"""Offline two-engine machine review of audio, never human listening verification.

Requires faster-whisper, sherpa-onnx, numpy, local model files, and sibling
transcript_diff.py only when --candidate is supplied. No models are downloaded.
Example: python audio_verify.py video.mp4 --runtime-root DIR --output-dir NEWDIR
"""

import argparse
import difflib
import importlib.metadata
import json
import math
from pathlib import Path
import shutil
import sys
import unicodedata
import wave


RATE = 16000
WINDOW_SECONDS = 24
DISCLAIMER = "原音双引擎机器复核；不是人工听审。识别一致不等于真实或100%正确，两个引擎可能同时出错。"


def normalize(text):
    """Ignore case/spacing/ordinary punctuation, never words or numeric symbols."""
    text = "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if not c.isspace())
    result = []
    for index, char in enumerate(text):
        if unicodedata.category(char).startswith("P"):
            numeric_neighbor = (index > 0 and text[index - 1].isdigit()) or (
                index + 1 < len(text) and text[index + 1].isdigit())
            if not (char in "-−+%‰.,/:" and numeric_neighbor):
                continue
        result.append(char)
    return "".join(result)


def text_diff(left, right):
    a, b = normalize(left), normalize(right)
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    edits = [{"operation": tag, "left_range": [i, j], "right_range": [k, m],
              "left": a[i:j], "right": b[k:m]}
             for tag, i, j, k, m in matcher.get_opcodes() if tag != "equal"]
    return {"normalized_equal": a == b, "similarity": round(matcher.ratio(), 4), "edits": edits}


def window_ranges(samples, rate=RATE):
    size = WINDOW_SECONDS * rate
    return [(start, min(start + size, samples)) for start in range(0, samples, size)]


def assign_whisper(segments, windows):
    """Word midpoint assignment is an alignment estimate, not verified timing."""
    texts = [[] for _ in windows]
    fallbacks = []
    for segment in segments:
        units = segment.get("words") or [segment]
        if not segment.get("words"):
            fallbacks.append(segment["id"])
        for unit in units:
            midpoint = (unit["start"] + unit["end"]) / 2
            index = next((i for i, w in enumerate(windows) if w["start"] <= midpoint < w["end"]), None)
            if index is None and windows:
                index = 0 if midpoint < windows[0]["start"] else len(windows) - 1
            if index is not None:
                texts[index].append(unit.get("word", unit.get("text", "")))
    return ["".join(parts) for parts in texts], fallbacks


def srt_time(seconds):
    total = max(0, round(seconds * 1000))
    hours, total = divmod(total, 3600000)
    minutes, total = divmod(total, 60000)
    secs, millis = divmod(total, 1000)
    return "{:02d}:{:02d}:{:02d},{:03d}".format(hours, minutes, secs, millis)


def write_json(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def write_wav(path, samples, np):
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(RATE)
        stream.writeframes(pcm)


def candidate_text(doc, start, end):
    if doc["format"] == "text":
        return "\n".join(e["text"] for e in doc["entries"]), [
            "纯文本没有时间码；假定候选文字对应本次选定音频范围，不能据此声称时间对齐。"]
    selected = [e for e in doc["entries"] if e["timing"]["end_ms"] / 1000 > start
                and e["timing"]["start_ms"] / 1000 < end]
    notes = []
    if not selected:
        notes.append("候选字幕在所选原音范围内没有重叠条目。")
    if any(e["timing"]["start_ms"] / 1000 < start or e["timing"]["end_ms"] / 1000 > end for e in selected):
        notes.append("候选字幕跨越选取边界；保留整个条目文字，边界处可能出现对照误差。")
    return "\n".join(e["text"] for e in selected), notes


def candidate_review(text, windows, field):
    """Map text-diff positions to estimated engine windows, not candidate timing."""
    parts = [normalize(w[field]) for w in windows]
    joined = "".join(parts)
    comparison = text_diff(joined, text)
    offsets, cursor = [], 0
    for part in parts:
        offsets.append((cursor, cursor + len(part)))
        cursor += len(part)
    touched = set()
    if not joined and normalize(text):
        touched.update(range(len(windows)))
    for edit in comparison["edits"]:
        start, end = edit["left_range"]
        matching = [i for i, (a, b) in enumerate(offsets) if start < b and end > a]
        if not matching and windows:
            matching = [next((i for i, (_, b) in enumerate(offsets) if b > start), len(windows) - 1)]
        touched.update(matching)
        edit["estimated_window_ids"] = [windows[i]["id"] for i in matching]
    comparison["location_note"] = "候选差异位置由引擎文字对齐估算，不能当作已核实的字词时间。"
    return comparison, touched


def model_paths(runtime):
    paths = {"whisper": runtime / "models/whisper-small",
             "sensevoice": runtime / "models/sensevoice/model.int8.onnx",
             "tokens": runtime / "models/sensevoice/tokens.txt"}
    required = [paths["whisper"] / n for n in ("model.bin", "config.json", "tokenizer.json")]
    required += [paths["sensevoice"], paths["tokens"]]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError("Missing local model files (no automatic download): " + ", ".join(missing))
    return paths


def run(args):
    source = args.media.resolve()
    destination = args.output_dir.resolve()
    if not source.is_file():
        raise ValueError("MEDIA must be an existing local file")
    if destination.exists() or args.output_dir.is_symlink():
        raise ValueError("--output-dir must be a new directory; existing paths are never reused")
    paths = model_paths(args.runtime_root.resolve())
    candidate = None
    if args.candidate:
        from transcript_diff import parse_document
        candidate = parse_document(args.candidate.resolve())
        errors = [i for i in candidate["issues"] if i["level"] == "error"]
        if errors:
            raise ValueError("Candidate format/read errors: " + json.dumps(errors, ensure_ascii=False))
    try:
        import numpy as np
        from faster_whisper import WhisperModel
        from faster_whisper.audio import decode_audio
        import sherpa_onnx
    except ImportError as exc:
        raise ValueError("Missing runtime dependency; install faster-whisper and sherpa-onnx in this Python environment: " + str(exc)) from exc
    audio = decode_audio(str(source), sampling_rate=RATE)
    first = round(args.start * RATE)
    last = len(audio) if args.duration is None else min(len(audio), first + round(args.duration * RATE))
    if first >= len(audio) or last <= first:
        raise ValueError("Selected audio range is empty or starts after the media ends")
    selected = audio[first:last]
    actual_start, actual_end = first / RATE, last / RATE
    ranges = window_ranges(len(selected))
    windows = [{"id": i + 1, "start": actual_start + a / RATE,
                "end": actual_start + b / RATE} for i, (a, b) in enumerate(ranges)]
    destination.mkdir(parents=True, exist_ok=False)
    try:
        print("Loading local CPU models; no download or candidate prompts.", flush=True)
        whisper = WhisperModel(str(paths["whisper"]), device="cpu", compute_type="int8",
                               cpu_threads=args.threads, num_workers=1, local_files_only=True)
        sense_language = "" if args.language == "auto" else args.language
        recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(paths["sensevoice"]), tokens=str(paths["tokens"]), num_threads=args.threads,
            sample_rate=RATE, provider="cpu", language=sense_language, use_itn=False)
        whisper_language = None if args.language == "auto" else ("zh" if args.language == "yue" else args.language)
        stream, info = whisper.transcribe(
            selected, language=whisper_language,
            beam_size=5, word_timestamps=True, condition_on_previous_text=False,
            vad_filter=False, temperature=0)
        segments = []
        for seg in stream:
            segments.append({"id": seg.id, "start": actual_start + seg.start,
                             "end": actual_start + seg.end, "text": seg.text,
                             "words": [{"word": w.word, "start": actual_start + w.start,
                                        "end": actual_start + w.end, "probability": w.probability}
                                       for w in (seg.words or [])]})
        whisper_texts, fallbacks = assign_whisper(segments, windows)
        whisper_raw = "\n".join(s["text"].strip() for s in segments)
        (destination / "whisper.raw.txt").write_text(whisper_raw + "\n", encoding="utf-8")
        with (destination / "whisper.raw.srt").open("x", encoding="utf-8", newline="\n") as handle:
            for i, seg in enumerate(segments, 1):
                handle.write("{}\n{} --> {}\n{}\n\n".format(i, srt_time(seg["start"]), srt_time(seg["end"]), seg["text"].strip()))
        for i, (a, b) in enumerate(ranges):
            sense_stream = recognizer.create_stream()
            sense_stream.accept_waveform(RATE, selected[a:b])
            recognizer.decode_stream(sense_stream)
            window = windows[i]
            window["whisper_text"] = whisper_texts[i]
            window["sensevoice_text"] = sense_stream.result.text
            window["rms"] = float(np.sqrt(np.mean(selected[a:b].astype(np.float64) ** 2)))
            window["engine_comparison"] = text_diff(window["whisper_text"], window["sensevoice_text"])
            window["review_reasons"] = []
            if not window["engine_comparison"]["normalized_equal"]:
                window["review_reasons"].append("两引擎文字不一致；包括可能的识别、跨窗和切分差异。")
            if not normalize(window["whisper_text"]) and not normalize(window["sensevoice_text"]) and window["rms"] >= 0.004:
                window["review_reasons"].append("两引擎均无文字但音量非低值；不据此判断有没有讲话。")
            print("SenseVoice window {}/{} complete.".format(i + 1, len(windows)), flush=True)
        sense_raw = "\n".join(w["sensevoice_text"] for w in windows)
        (destination / "sensevoice.raw.txt").write_text(sense_raw + "\n", encoding="utf-8")
        candidate_report = None
        if candidate is not None:
            text, notes = candidate_text(candidate, actual_start, actual_end)
            candidate_report = {"path": candidate["path"], "format": candidate["format"],
                                "selected_text": text, "notes": notes, "issues": candidate["issues"]}
            for field in ("whisper_text", "sensevoice_text"):
                comparison, touched = candidate_review(text, windows, field)
                candidate_report[field] = comparison
                for index in touched:
                    windows[index]["review_reasons"].append("候选文字与{}有差异；位置为机器估算。".format(field))
            shutil.copyfile(args.candidate, destination / ("candidate.raw" + args.candidate.suffix))
        clip_dir = destination / "review_clips"
        review_ids = []
        for i, window in enumerate(windows):
            if window["review_reasons"]:
                clip_dir.mkdir(exist_ok=True)
                clip = clip_dir / "window_{:04d}.wav".format(window["id"])
                a, b = ranges[i]
                write_wav(clip, selected[a:b], np)
                window["review_clip"] = "review_clips/" + clip.name
                review_ids.append(window["id"])
        versions = {package: importlib.metadata.version(package) for package in ("faster-whisper", "sherpa-onnx", "numpy")}
        evidence = {"schema_version": 1, "status": "complete", "review_type": DISCLAIMER,
                    "media": str(source), "sample_rate": RATE,
                    "range": {"start": actual_start, "end": actual_end, "seconds": len(selected) / RATE},
                    "models": {key: str(value) for key, value in paths.items()}, "versions": versions,
                    "settings": {"requested_language": args.language, "whisper_language": whisper_language,
                                 "sensevoice_language": sense_language,
                                 "whisper_condition_on_previous_text": False, "whisper_word_timestamps": True,
                                 "sensevoice_use_itn": False, "sensevoice_window_seconds": WINDOW_SECONDS},
                    "whisper_language": info.language, "whisper_segments": segments,
                    "sensevoice_timing_note": "SenseVoice时间范围是实际送入引擎的音频窗口，不是逐字定位结果。",
                    "whisper_timing_note": "Whisper时间戳为引擎估计；SRT使用原媒体坐标，未平移到片段零点。",
                    "word_timing_fallback_segment_ids": fallbacks, "windows": windows}
        write_json(destination / "audio_evidence.json", evidence)
        report = {"schema_version": 1, "status": "complete", "review_type": DISCLAIMER,
                  "window_count": len(windows), "review_window_count": len(review_ids),
                  "review_window_ids": review_ids, "candidate": candidate_report,
                  "normalization": "只忽略大小写、空白和普通标点；保留字词、数字及相邻数值符号，不改人名/否定/繁简/数字写法。",
                  "limits": ["两个模型可能同时漏听、幻听或认错。", "固定窗口和词中点分配会产生边界误差；查看WAV和原文。",
                             "未做人工听审，也未验证候选文是否完整覆盖整个源视频。",
                             "无分歧仅表示本次归一文本一致；无文字不代表音频无人声。"],
                  "windows": [{k: w[k] for k in ("id", "start", "end", "whisper_text", "sensevoice_text", "engine_comparison", "review_reasons")}
                              | ({"review_clip": w["review_clip"]} if "review_clip" in w else {}) for w in windows]}
        write_json(destination / "review_report.json", report)
        print("Machine review complete: {} ({} review windows)".format(destination, len(review_ids)), flush=True)
        return 0
    except Exception as exc:
        write_json(destination / "failure.json", {"status": "failed", "error": str(exc), "review_type": DISCLAIMER})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("media", type=Path)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--language", default="zh", choices=("zh", "en", "ja", "ko", "yue", "auto"))
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    if not math.isfinite(args.start) or args.start < 0 or args.threads < 1:
        parser.error("--start must be finite and nonnegative; --threads must be positive")
    if args.duration is not None and (not math.isfinite(args.duration) or args.duration <= 0):
        parser.error("--duration must be finite and positive")
    try:
        return run(args)
    except Exception as exc:
        print("Audio review failed: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
