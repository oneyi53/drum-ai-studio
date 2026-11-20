#!/usr/bin/env python3
"""Prepare openly licensed full-song material for kick-detection evaluation.

OnAir is the stem-backed reference set. Only the two tracks whose source config
contains a dedicated Kick.wav are scored automatically; other grouped-drum
tracks are retained as bass-confusion listening cases, never mislabeled as
kick-only ground truth.

Kaino is queried through its public Library MCP endpoint. Its full mixes are
robustness inputs only until independent kick annotations have been reviewed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import numpy as np
import requests

ONAIR_BASE = "https://media.githubusercontent.com/media/sevagh/OnAir-Music-Dataset/main"
ONAIR_FILES = [
    "OnAir-Music-Dataset-v4-misc.zip",
    "OnAir-Music-Dataset-v4-LoFi-Vol-3.zip",
]
ONAIR_LICENSE = "CC BY-SA 4.0"
KAINO_ENDPOINT = "https://kaino.dev/mcp"
KAINO_LICENSE = "CC0 1.0"


def audio_metadata(path: Path) -> dict[str, Any]:
    import soundfile as sf
    info = sf.info(str(path))
    return {"sample_rate": int(info.samplerate), "duration_seconds": float(info.duration), "channels": int(info.channels)}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 100_000:
        return
    partial = destination.with_suffix(destination.suffix + ".part")
    with requests.get(url, stream=True, timeout=(30, 180)) as response:
        response.raise_for_status()
        with partial.open("wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    output.write(chunk)
    partial.replace(destination)


def unpack_onair(root: Path) -> list[Path]:
    archives = root / "downloads"
    extracted = root / "onair"
    for name in ONAIR_FILES:
        archive = archives / name
        download(f"{ONAIR_BASE}/{name}", archive)
        if not zipfile.is_zipfile(archive):
            raise RuntimeError(
                f"{archive} is not a ZIP (possibly an LFS pointer); "
                "use the Git LFS media URL and inspect the response"
            )
        with zipfile.ZipFile(archive) as bundle:
            extraction_records = []
            for member in bundle.infolist():
                source_name = PurePosixPath(member.filename)
                if source_name.is_absolute() or ".." in source_name.parts:
                    raise RuntimeError(f"Unsafe archive member path: {member.filename!r}")
                safe_parts = []
                for part in source_name.parts:
                    safe = "".join("_" if ord(ch) < 32 or ch in '<>:"|?*' else ch for ch in part).rstrip(" .")
                    if not safe:
                        safe = "_file"
                    if safe != part:
                        safe += "." + hashlib.sha256(part.encode("utf-8")).hexdigest()[:8]
                    safe_parts.append(safe)
                relative = Path(*safe_parts)
                destination = extracted / relative
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                # Do not materialize symlinks from untrusted ZIP members.
                mode = (member.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, destination.open("wb") as target:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        target.write(chunk)
                extraction_records.append({"archive": name, "source_member": member.filename,
                                           "extracted_path": str(destination)})
            (root / "onair-extraction-manifest.json").write_text(
                json.dumps(extraction_records, indent=2, ensure_ascii=False), encoding="utf-8"
            )
    return list(extracted.rglob("*.wav"))


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def inspect_onair(root: Path, wavs: list[Path]) -> list[dict[str, Any]]:
    by_name = {normalize_name(path.name): path for path in wavs}
    track_specs = [
        {
            "track": "Under My Skin - OnAir Music",
            "mix": "Under My Skin - OnAir Music.wav",
            "kick": "Kick.wav",
            "drums": ["Break Drums.wav", "Build Drums.wav", "Kick.wav", "Snare.wav"],
            "bass": ["Bass.wav"],
            "tier": "scored_candidate",
            "reason": "Dedicated isolated Kick.wav and separate Bass.wav are mapped by onair-py.",
        },
        {
            "track": "Set Me Free - OnAir Music",
            "mix": "Set Me Free - OnAir Music.wav",
            "kick": "Kick.wav",
            "drums": ["Hats.wav", "Kick.wav", "Snare.wav"],
            "bass": ["Bass.wav"],
            "tier": "scored_candidate",
            "reason": "Dedicated isolated Kick.wav and separate Bass.wav are mapped by onair-py.",
        },
        {
            "track": "Ronin - OnAir Music",
            "mix": "Ronin - OnAir Music.wav",
            "kick": None,
            "drums": ["Ronin ft. KXNE Stems - Drums.wav"],
            "bass": ["Ronin ft. KXNE Stems - 808.wav"],
            "tier": "bass_confusion_only",
            "reason": "Drums are grouped; 808 is separately available, but no kick-only reference.",
        },
        {
            "track": "Yaku - OnAir Music",
            "mix": "Yaku - OnAir Music.wav",
            "kick": None,
            "drums": ["Idea 3 Stems - Drums.wav"],
            "bass": ["Idea 3 Stems - Bass.wav"],
            "tier": "bass_confusion_only",
            "reason": "Drums are grouped with no dedicated kick stem.",
        },
        {
            "track": "Ramen Rain - OnAir Music",
            "mix": "Ramen Rain - OnAir Music.wav",
            "kick": None,
            "drums": ["Idea 2 Stems - Drums.wav", "Idea 2 Stems - Brshes.wav"],
            "bass": ["Idea 2 Stems - Bass.wav"],
            "tier": "bass_confusion_only",
            "reason": "Drums/brushes are grouped; no dedicated kick stem.",
        },
        {
            "track": "Bouncin Around - OnAir Music",
            "mix": "Bouncin Around - OnAir Music.wav",
            "kick": None,
            "drums": ["Idea 1 Stems - Drums.wav", "Idea 1 Stems - Brushes.wav", "Idea 1 Stems - Tambo.wav"],
            "bass": ["Idea 1 Stems - Bass.wav"],
            "tier": "bass_confusion_only",
            "reason": "Drums/brushes/tambo are grouped; no dedicated kick stem.",
        },
    ]
    results: list[dict[str, Any]] = []
    for spec in track_specs:
        candidates = list(extracted_candidates(root / "onair", spec["track"]))
        track_files = {normalize_name(p.name): p for p in candidates}
        row: dict[str, Any] = {
            "dataset": "OnAir Music Dataset V4",
            "license": ONAIR_LICENSE,
            "track": spec["track"],
            "tier": spec["tier"],
            "reason": spec["reason"],
            "source_url": "https://github.com/sevagh/OnAir-Music-Dataset",
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "mix_path": None,
            "mix_sha256": None,
            "kick_stem_path": None,
            "kick_stem_sha256": None,
            "bass_stem_paths": [],
            "drum_stem_paths": [],
        }
        mix = track_files.get(normalize_name(spec["mix"]))
        if mix:
            row["mix_path"] = str(mix)
            row["mix_sha256"] = sha256(mix)
            row["mix_audio_metadata"] = audio_metadata(mix)
        if spec["kick"]:
            kick = track_files.get(normalize_name(spec["kick"]))
            if kick:
                row["kick_stem_path"] = str(kick)
                row["kick_stem_sha256"] = sha256(kick)
                row["kick_audio_metadata"] = audio_metadata(kick)
            else:
                row["tier"] = "unusable_missing_expected_kick"
                row["reason"] += " Expected Kick.wav not found in extracted track folder."
        for name in spec["bass"]:
            item = track_files.get(normalize_name(name))
            if item:
                row["bass_stem_paths"].append({"path": str(item), "sha256": sha256(item), **audio_metadata(item)})
        for name in spec["drums"]:
            item = track_files.get(normalize_name(name))
            if item:
                row["drum_stem_paths"].append({"path": str(item), "sha256": sha256(item), **audio_metadata(item)})
        if not mix:
            row["tier"] = "unusable_missing_mix"
        results.append(row)
    return results


def extracted_candidates(root: Path, track: str):
    target = normalize_name(track)
    for path in root.rglob("*.wav"):
        parent = normalize_name(path.parent.name)
        if target in parent or parent in target:
            yield path


class KainoMCP:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        })
        self.session_id: str | None = None
        self.protocol = "2025-03-26"
        self.request_id = 0

    def post(self, payload: dict[str, Any]) -> Any:
        headers = {"MCP-Protocol-Version": self.protocol}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        response = self.session.post(self.endpoint, json=payload, headers=headers, timeout=90)
        response.raise_for_status()
        self.session_id = response.headers.get("Mcp-Session-Id", self.session_id)
        raw = response.text.strip()
        if not raw:
            return {}
        if raw.startswith("event:") or "\ndata:" in raw:
            data_lines = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")]
            raw = data_lines[-1] if data_lines else raw
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}

    def initialize(self) -> None:
        result = self.post({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": self.protocol,
                "capabilities": {},
                "clientInfo": {"name": "drum-ai-studio-corpus-prep", "version": "1.0.0"},
            },
        })
        if "error" in result:
            raise RuntimeError(f"Kaino MCP initialize failed: {result['error']}")
        self.post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self.request_id += 1
        result = self.post({
            "jsonrpc": "2.0",
            "id": self.request_id + 1,
            "method": method,
            "params": params or {},
        })
        if "error" in result:
            raise RuntimeError(f"Kaino MCP {method} failed: {result['error']}")
        return result.get("result", result)


def schema_args(tool: dict[str, Any], query: str, item: dict[str, Any] | None = None) -> dict[str, Any]:
    schema = tool.get("inputSchema", {})
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    args: dict[str, Any] = {}
    item = item or {}
    for key, spec in properties.items():
        low = key.lower()
        if any(word in low for word in ("query", "search", "term")):
            args[key] = query
        elif any(word in low for word in ("item_id", "resource_id", "track_id", "id", "slug")):
            value = next((item[k] for k in (key, "id", "item_id", "resource_id", "track_id", "slug") if k in item), None)
            if value is not None:
                args[key] = value
        elif "format" in low or "extension" in low:
            args[key] = "wav"
        elif "type" in low or "kind" in low or "collection" in low:
            args[key] = "music"
        elif "limit" in low or "page_size" in low:
            args[key] = 50
        elif key in required:
            if spec.get("type") == "string":
                args[key] = query
            elif spec.get("type") == "integer":
                args[key] = 50
    return args


def flatten_json(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from flatten_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from flatten_json(child)


def kaino_search(root: Path) -> dict[str, Any]:
    client = KainoMCP(KAINO_ENDPOINT)
    client.initialize()
    tool_list = client.call("tools/list")
    tools = tool_list.get("tools", [])
    by_name = {tool["name"]: tool for tool in tools}
    search_tool = next((tool for name, tool in by_name.items() if "search_library" in name), None)
    if not search_tool:
        raise RuntimeError(f"Kaino MCP search_library tool not found. Available: {list(by_name)}")

    queries = [
        "acoustic folk instrumental",
        "afrobeat instrumental",
        "hip hop instrumental",
        "jazz instrumental",
        "ambient electronic instrumental",
        "cinematic orchestral instrumental",
    ]
    searches: list[dict[str, Any]] = []
    for query in queries:
        result = client.call(
            "tools/call",
            {"name": search_tool["name"], "arguments": schema_args(search_tool, query)},
        )
        searches.append({"query": query, "result": result})

    (root / "kaino-search-results.json").write_text(
        json.dumps({"tools": tools, "searches": searches}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {"tool_names": list(by_name), "search_count": len(searches), "result_path": str(root / "kaino-search-results.json")}


def propose_kick_onsets(kick_path: Path, output_csv: Path) -> int:
    import librosa

    waveform, sr = librosa.load(str(kick_path), sr=None, mono=True)
    if waveform.size == 0:
        return 0
    hop = 128
    onset_env = librosa.onset.onset_strength(y=waveform, sr=sr, hop_length=hop, aggregate=np.median)
    # Low minimum separation avoids merging fast double-kicks. This is an onset
    # proposal only: a human must listen to the isolated stem and approve it.
    peaks = librosa.util.peak_pick(
        onset_env, pre_max=2, post_max=2, pre_avg=4, post_avg=4,
        delta=max(float(np.max(onset_env)) * 0.08, 0.02), wait=max(1, int(0.075 * sr / hop)),
    )
    times = librosa.frames_to_time(peaks, sr=sr, hop_length=hop)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "track", "time_seconds", "label", "source", "review_status", "reviewer", "notes"
        ])
        writer.writeheader()
        for value in times:
            writer.writerow({
                "track": kick_path.parent.name,
                "time_seconds": f"{float(value):.6f}",
                "label": "kick",
                "source": "isolated_kick_stem_onset_proposal",
                "review_status": "needs_human_review",
                "reviewer": "",
                "notes": "Confirm onset against isolated Kick.wav and full mix; do not score until approved.",
            })
    return len(times)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/real-song-corpus"))
    parser.add_argument("--skip-kaino", action="store_true")
    args = parser.parse_args()
    root = args.output
    root.mkdir(parents=True, exist_ok=True)

    wavs = unpack_onair(root)
    onair = inspect_onair(root, wavs)
    for row in onair:
        if row.get("kick_stem_path"):
            path = Path(row["kick_stem_path"])
            proposal = root / "annotations" / (normalize_name(row["track"]).replace(" ", "-") + ".csv")
            row["kick_onset_proposals"] = propose_kick_onsets(path, proposal)
            row["proposal_csv"] = str(proposal)
    (root / "onair-manifest.json").write_text(json.dumps(onair, indent=2, ensure_ascii=False), encoding="utf-8")

    kaino_result = {"status": "skipped"}
    if not args.skip_kaino:
        try:
            kaino_result = {"status": "ok", **kaino_search(root)}
        except Exception as exc:  # preserve OnAir artifacts if the MCP endpoint is unavailable
            kaino_result = {"status": "unavailable", "error": repr(exc)}
    (root / "kaino-status.json").write_text(json.dumps(kaino_result, indent=2), encoding="utf-8")

    print(json.dumps({
        "onair_tracks": len(onair),
        "onair_scored_candidates": sum(row["tier"] == "scored_candidate" for row in onair),
        "onair_bass_confusion_only": sum(row["tier"] == "bass_confusion_only" for row in onair),
        "kick_proposals": sum(int(row.get("kick_onset_proposals", 0)) for row in onair),
        "kaino": kaino_result,
        "manifest": str(root / "onair-manifest.json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
