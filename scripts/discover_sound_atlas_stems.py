#!/usr/bin/env python3
"""Discover Sound Atlas tracks with both drum and bass layers.

This is a metadata-only discovery pass. The source dataset describes 2,740
instrument-layer rows, not 2,740 independent songs. Track credits and original
licences must be checked per ID before any download is admitted to training.
"""
from __future__ import annotations
import argparse, json, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import requests

REPO="kvnloo/sound-atlas-stems"
API=f"https://huggingface.co/api/datasets/{REPO}/tree/main"
RAW=f"https://huggingface.co/datasets/{REPO}/resolve/main/"

def classify_stem(key: str) -> str:
    value=re.sub(r"[^a-z0-9]+","",str(key).lower())
    if value in {"drum","drums","drumstem"}: return "drums"
    if value in {"bass","bassstem"}: return "bass"
    return value or "unknown"

def build_candidates(index: dict, max_tracks: int=250) -> list[dict]:
    tracks=index.get("tracks",{})
    candidates=[]
    for track_id, data in sorted(tracks.items()):
        stems=data.get("stems",[])
        kinds={classify_stem(x.get("k","")) for x in stems}
        if not {"drums","bass"}.issubset(kinds): continue
        candidates.append({
            "track_id":str(track_id),
            "duration_seconds":float(data.get("dur",0) or 0),
            "stem_kinds":sorted(kinds),
            "drum_and_bass_layers_present":True,
            "stems":[{"kind":classify_stem(x.get("k","")),"file":x.get("f"),"active_fraction":x.get("on")} for x in stems],
            "source_dataset":REPO,
            "source_credit_file":"CREDITS.md",
            "license":"CC0 or CC BY (dataset card claim; resolve per-track credit)",
            "license_verified_per_track":False,
            "kick_isolated":False,
            "audio_downloaded":False,
            "review_status":"awaiting_per_track_credit_and_audio_review"
        })
        if len(candidates)>=max_tracks: break
    return candidates

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--max-tracks",type=int,default=250)
    a=p.parse_args()
    session=requests.Session(); session.headers["User-Agent"]="DrumAI-Studio-open-audio-discovery"
    listing=session.get(API+"?recursive=true",timeout=90); listing.raise_for_status()
    files=listing.json()
    by_name={Path(x.get("path","")).name:x.get("path") for x in files if x.get("type")=="file"}
    index_path=by_name.get("stems.json")
    credits_path=by_name.get("CREDITS.md")
    if not index_path or not credits_path:
        raise RuntimeError("Sound Atlas repository is missing stems.json or CREDITS.md")
    index_response=session.get(RAW+quote(index_path,safe="/"),timeout=90); index_response.raise_for_status()
    credits_response=session.get(RAW+quote(credits_path,safe="/"),timeout=90); credits_response.raise_for_status()
    index=index_response.json()
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/"sound-atlas-stems-index.json").write_text(json.dumps(index),encoding="utf-8")
    (a.output/"sound-atlas-CREDITS.md").write_text(credits_response.text,encoding="utf-8")
    candidates=build_candidates(index,a.max_tracks)
    report={"created_at_utc":datetime.now(timezone.utc).isoformat(),"dataset":REPO,
            "source_url":f"https://huggingface.co/datasets/{REPO}",
            "dataset_card_license":"CC BY 4.0 for dataset package; original tracks are described as CC0 or CC BY",
            "metadata_layer_rows":2740,"unique_tracks_in_index":len(index.get("tracks",{})),
            "candidate_tracks_with_drums_and_bass":len(candidates),
            "important_limit":"Drums stem is not kick-isolated. No track is rights-verified until CREDITS.md is matched to its ID and original source.",
            "candidates":candidates}
    (a.output/"sound-atlas-candidates.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("unique_tracks_in_index","candidate_tracks_with_drums_and_bass","important_limit")},indent=2))
if __name__=="__main__": main()
