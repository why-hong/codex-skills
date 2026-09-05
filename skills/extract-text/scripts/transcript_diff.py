#!/usr/bin/env python3
"""Compare transcript text and actual subtitle timing; never verify audio/meaning.

Usage: python transcript_diff.py RAW CORRECTED --output REPORT.json
UTF-8 (with optional BOM) is required. .srt and .vtt are parsed strictly; other
extensions are treated as plain text. Existing output files are never replaced.
Exit codes: 0 = valid comparison, 2 = input/format/output error.
"""

import argparse
import difflib
import json
import re
import sys
from pathlib import Path


SRT_TIME = re.compile(r"^(\d{2,}):([0-5]\d):([0-5]\d),(\d{3})$")
VTT_TIME = re.compile(r"^(?:(\d{2,}):)?([0-5]\d):([0-5]\d)\.(\d{3})$")


def issue(level, code, message, line=None):
    item = {"level": level, "code": code, "message": message}
    if line is not None:
        item["line"] = line
    return item


def milliseconds(value, kind):
    match = (SRT_TIME if kind == "srt" else VTT_TIME).fullmatch(value)
    if not match:
        raise ValueError("Invalid {} timecode: {!r}".format(kind.upper(), value))
    hours, minutes, seconds, millis = match.groups()
    return ((int(hours or 0) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis)


def blocks(lines, offset=0):
    current = []
    start = offset + 1
    for number, line in enumerate(lines, offset + 1):
        if not line.strip():
            if current:
                yield start, current
                current = []
        else:
            if not current:
                start = number
            current.append(line)
    if current:
        yield start, current


def parse_document(path):
    suffix = path.suffix.lower()
    kind = {".srt": "srt", ".vtt": "vtt"}.get(suffix, "text")
    doc = {"path": str(path), "format": kind, "entries": [], "metadata": [], "issues": []}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        doc["issues"].append(issue("error", "input_read_error", str(exc)))
        return doc
    lines = text.splitlines()
    if kind == "text":
        doc["entries"] = [{"entry": n, "line": n, "text": value}
                          for n, value in enumerate(lines, 1)]
        return doc
    offset = 0
    if kind == "vtt":
        if not lines or not re.fullmatch(r"WEBVTT(?:[ \t].*)?", lines[0]) or "-->" in lines[0]:
            doc["issues"].append(issue("error", "invalid_vtt_header", "VTT must begin with WEBVTT.", 1))
            return doc
        header = [lines[0]]
        offset = 1
        while offset < len(lines) and lines[offset].strip():
            # A cue immediately after WEBVTT is a missing header separator.
            if "-->" in lines[offset]:
                doc["issues"].append(issue("error", "missing_header_separator",
                                           "VTT header requires a blank line before cues.", offset + 1))
                return doc
            header.append(lines[offset])
            offset += 1
        doc["metadata"].append({"type": "header", "text": "\n".join(header)})
    subtitle_blocks = 0
    identifiers = set()
    previous_start = None
    for first_line, block in blocks(lines[offset:], offset):
        if kind == "vtt" and (re.match(r"^NOTE(?:[ \t]|$)", block[0]) or block[0] in {"STYLE", "REGION"}):
            doc["metadata"].append({"type": block[0].split()[0], "text": "\n".join(block)})
            continue
        subtitle_blocks += 1
        identifier = None
        timing_index = 0
        if kind == "srt":
            if not re.fullmatch(r"[0-9]+", block[0]):
                doc["issues"].append(issue("error", "invalid_srt_index",
                                           "Each SRT block must begin with a numeric cue index.", first_line))
                continue
            identifier = block[0]
            timing_index = 1
        elif "-->" not in block[0]:
            identifier = block[0]
            timing_index = 1
        if timing_index >= len(block):
            doc["issues"].append(issue("error", "missing_timing", "Cue has no timing line.", first_line))
            continue
        timing = block[timing_index]
        match = re.fullmatch(r"(\S+)[ \t]+-->[ \t]+(\S+)(?:[ \t]+(.*))?", timing)
        if not match:
            doc["issues"].append(issue("error", "invalid_timing_line",
                                       "Expected START --> END on the cue timing line.", first_line + timing_index))
            continue
        start, end, settings = match.groups()
        settings = settings or ""
        try:
            start_ms, end_ms = milliseconds(start, kind), milliseconds(end, kind)
        except ValueError as exc:
            doc["issues"].append(issue("error", "invalid_timecode", str(exc), first_line + timing_index))
            continue
        if end_ms <= start_ms:
            doc["issues"].append(issue("error", "invalid_duration",
                                       "Cue end must be later than cue start.", first_line + timing_index))
        if settings and kind == "srt":
            doc["issues"].append(issue("error", "unsupported_srt_timing_suffix",
                                       "SRT timing-line suffixes are not supported.", first_line + timing_index))
        payload = block[timing_index + 1:]
        if not payload:
            doc["issues"].append(issue("error", "missing_text", "Cue has no text payload.", first_line))
        # A second timing line usually means the required cue separator is missing.
        if any("-->" in value for value in payload):
            doc["issues"].append(issue("error", "arrow_in_payload",
                                       "Cue payload contains -->; check for a missing blank-line separator.", first_line))
        if identifier is not None:
            if identifier in identifiers:
                doc["issues"].append(issue("warning", "duplicate_identifier", "Duplicate cue identifier.", first_line))
            identifiers.add(identifier)
        if previous_start is not None and start_ms < previous_start:
            doc["issues"].append(issue("warning", "out_of_order_start", "Cue starts earlier than the preceding cue.", first_line))
        previous_start = start_ms
        doc["entries"].append({"entry": subtitle_blocks, "line": first_line,
                               "identifier": identifier, "text": "\n".join(payload),
                               "timing": {"start": start, "end": end,
                                          "start_ms": start_ms, "end_ms": end_ms},
                               "settings": settings})
    doc["subtitle_blocks_seen"] = subtitle_blocks
    if not subtitle_blocks:
        doc["issues"].append(issue("warning", "no_cues", "No subtitle cue blocks found."))
    return doc


def public_document(doc):
    return {key: value for key, value in doc.items() if key != "entries"} | {"entry_count": len(doc["entries"])}


def compare(raw, corrected):
    left, right = raw["entries"], corrected["entries"]
    changes = []
    counts = {"added": 0, "removed": 0, "text_modified": 0,
              "timing_modified": 0, "identifier_modified": 0, "settings_modified": 0}
    matcher = difflib.SequenceMatcher(a=[item["text"] for item in left],
                                     b=[item["text"] for item in right], autojunk=False)
    alignment_notes = []
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag == "replace" and (a1 - a0 > 1 or b1 - b0 > 1):
            alignment_notes.append({"raw_entries": [a0 + 1, a1], "corrected_entries": [b0 + 1, b1],
                                    "note": "Unmatched replacement block paired by position; alignment may be ambiguous."})
        paired = min(a1 - a0, b1 - b0) if tag in {"equal", "replace"} else 0
        for offset in range(paired):
            old, new = left[a0 + offset], right[b0 + offset]
            fields = [key for key in ("text", "timing", "identifier", "settings") if old.get(key) != new.get(key)]
            if fields:
                changes.append({"kind": "modified", "fields": fields, "raw": old, "corrected": new})
                for field in fields:
                    counts[field + "_modified"] += 1
        for old in left[a0 + paired:a1]:
            changes.append({"kind": "removed", "raw": old, "corrected": None})
            counts["removed"] += 1
        for new in right[b0 + paired:b1]:
            changes.append({"kind": "added", "raw": None, "corrected": new})
            counts["added"] += 1
    comparable_timing = raw["format"] != "text" and corrected["format"] != "text"
    values_changed = notation_changed = None
    if comparable_timing:
        values_changed = [[e["timing"][k] for k in ("start_ms", "end_ms")] for e in left] != [
            [e["timing"][k] for k in ("start_ms", "end_ms")] for e in right]
        notation_changed = [[e["timing"][k] for k in ("start", "end")] for e in left] != [
            [e["timing"][k] for k in ("start", "end")] for e in right]
    return {"entry_count_changed": len(left) != len(right), "change_counts": counts,
            "timing": {"comparable": comparable_timing, "timestamp_values_changed": values_changed,
                       "timestamp_notation_changed": notation_changed,
                       "note": "Timing sequence comparison includes cue additions/removals. Null means timing is unavailable in at least one input."},
            "metadata_changed": raw["metadata"] != corrected["metadata"],
            "alignment": "Exact text anchors, then positional pairing inside replacement blocks; no semantic alignment.",
            "alignment_notes": alignment_notes, "changes": changes}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("raw", type=Path)
    parser.add_argument("corrected", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raw_path, corrected_path, output_path = args.raw.resolve(), args.corrected.resolve(), args.output.resolve()
    if output_path in {raw_path, corrected_path}:
        parser.error("--output must not refer to either input file")
    if output_path.exists() or args.output.is_symlink():
        parser.error("--output already exists; choose a new output path")
    raw, corrected = parse_document(raw_path), parse_document(corrected_path)
    invalid = any(i["level"] == "error" for doc in (raw, corrected) for i in doc["issues"])
    report = {"schema_version": 1, "status": "invalid" if invalid else "compared",
              "scope": "Text and subtitle structure comparison only; no audio, meaning, or transcription accuracy verification.",
              "normalization": "UTF-8 BOM removed; CRLF/LF normalized; plain text compared by lines, excluding terminal newline style.",
              "raw": public_document(raw), "corrected": public_document(corrected),
              "comparison": None if invalid else compare(raw, corrected)}
    try:
        with output_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except OSError as exc:
        print("Cannot create report: {}".format(exc), file=sys.stderr)
        return 2
    print("{}: {}".format(report["status"], output_path))
    return 2 if invalid else 0


if __name__ == "__main__":
    sys.exit(main())
