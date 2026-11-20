"""Resolve Kaino CC0 music search results into local WAV files.

This script intentionally uses Kaino's documented public Library MCP tools
rather than guessing CDN URLs or scraping hidden page implementation details.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ENDPOINT = "https://kaino.dev/mcp"


class MCP:
    def __init__(self):
        self.http = requests.Session()
        self.http.headers.update({"Accept": "application/json, text/event-stream", "Content-Type": "application/json"})
        self.session_id = None
        self.seq = 0

    def post(self, payload):
        headers = {"MCP-Protocol-Version": "2025-03-26"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        response = self.http.post(ENDPOINT, json=payload, headers=headers, timeout=90)
        response.raise_for_status()
        self.session_id = response.headers.get("Mcp-Session-Id", self.session_id)
        raw = response.text.strip()
        if not raw:
            return {}
        if raw.startswith("event:") or "\ndata:" in raw:
            raw = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")][-1]
        return json.loads(raw)

    def request(self, method, params=None):
        self.seq += 1
        result = self.post({"jsonrpc": "2.0", "id": self.seq, "method": method, "params": params or {}})
        if "error" in result:
            raise RuntimeError(result["error"])
        return result.get("result", result)

    def connect(self):
        self.request("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "drum-ai-studio-kaino-fetch", "version": "1.0.0"},
        })
        self.post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)
    elif isinstance(value, str) and value[:1] in "[{":
        try:
            yield from walk(json.loads(value))
        except json.JSONDecodeError:
            pass


def call_tool(client: MCP, tool: dict[str, Any], query: str, item: dict[str, Any] | None = None):
    item = item or {}
    schema = tool.get("inputSchema", {})
    props = schema.get("properties", {})
    required = schema.get("required", [])
    args = {}
    for key, spec in props.items():
        low = key.lower()
        if any(x in low for x in ("query", "search", "term")):
            args[key] = query
        elif any(x in low for x in ("item_id", "resource_id", "track_id", "id", "slug")):
            for candidate in (key, "id", "item_id", "resource_id", "track_id", "slug"):
                if candidate in item:
                    args[key] = item[candidate]
                    break
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
    return client.request("tools/call", {"name": tool["name"], "arguments": args})


def candidates(payload: Any):
    seen = set()
    for obj in walk(payload):
        title = obj.get("title") or obj.get("name") or obj.get("track_title")
        identifier = next((obj[k] for k in ("id", "item_id", "resource_id", "track_id", "slug") if obj.get(k) is not None), None)
        if title and identifier is not None:
            key = str(identifier)
            if key not in seen:
                seen.add(key)
                yield {"title": str(title), "id": identifier, **obj}


def audio_urls(payload: Any):
    seen = set()
    for obj in walk(payload):
        for key, value in obj.items():
            if isinstance(value, str) and value.startswith("https://"):
                low = (key + " " + value).lower()
                if any(ext in low for ext in (".wav", ".mp3", "download")):
                    if value not in seen:
                        seen.add(value)
                        yield value
    if isinstance(payload, dict):
        raw = payload.get("raw", "")
        for token in raw.split():
            match = token.strip(chr(34) + "'<>),.;")
            if match.startswith("https://") and any(ext in match.lower() for ext in (".wav", ".mp3", "download")) and match not in seen:
                yield match


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--search-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-tracks", type=int, default=12)
    args = parser.parse_args()

    previous = json.loads(args.search_json.read_text(encoding="utf-8"))
    client = MCP()
    client.connect()
    tool_list = client.request("tools/list").get("tools", [])
    by_name = {tool["name"]: tool for tool in tool_list}
    get_item = next((v for k, v in by_name.items() if "get_library_item" in k), None)
    get_download = next((v for k, v in by_name.items() if "get_library_download" in k), None)
    if not get_download:
        raise RuntimeError(f"get_library_download unavailable; tools={list(by_name)}")

    selected = []
    seen = set()
    for search in previous.get("searches", []):
        for item in candidates(search.get("result")):
            if str(item["id"]) not in seen:
                seen.add(str(item["id"]))
                selected.append(item)
                break
        if len(selected) >= args.max_tracks:
            break

    args.output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for item in selected:
        payload = item
        if get_item:
            payload = call_tool(client, get_item, item["title"], item)
        download_payload = call_tool(client, get_download, item["title"], item)
        urls = list(audio_urls(download_payload)) or list(audio_urls(payload))
        if not urls:
            manifest.append({"title": item["title"], "id": item["id"], "license": "CC0 1.0", "status": "no_download_url", "download_response": download_payload})
            continue
        url = urls[0]
        extension = ".wav" if ".wav" in url.lower() else ".mp3"
        safe = re.sub(r"[^a-z0-9]+", "-", item["title"].lower()).strip("-")
        destination = args.output / f"{safe}{extension}"
        if not destination.exists():
            with requests.get(url, stream=True, timeout=(30, 180)) as response:
                response.raise_for_status()
                with destination.open("wb") as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            stream.write(chunk)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        manifest.append({
            "dataset": "Kaino Free Music Library",
            "title": item["title"],
            "source_id": item["id"],
            "source_url": "https://kaino.dev/library/music",
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "license": "CC0 1.0",
            "file": str(destination),
            "sha256": digest,
            "bytes": destination.stat().st_size,
            "audio_metadata": {"sample_rate": __import__("soundfile").info(str(destination)).samplerate, "duration_seconds": __import__("soundfile").info(str(destination)).duration, "channels": __import__("soundfile").info(str(destination)).channels},
            "role": "full_mix_robustness_only_until_human_kick_annotation",
            "status": "downloaded",
        })
    (args.output / "kaino-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"selected": len(selected), "downloaded": sum(x["status"] == "downloaded" for x in manifest), "manifest": str(args.output / "kaino-manifest.json")}, indent=2))


if __name__ == "__main__":
    main()
