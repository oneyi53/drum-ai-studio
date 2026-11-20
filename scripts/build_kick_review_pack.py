#!/usr/bin/env python3
"""Build a human-review queue for kick and low-frequency transient events."""
from __future__ import annotations
import argparse, csv, hashlib, json
from pathlib import Path
from typing import Any

LABELS = ("kick", "bass_guitar", "bass_synth_808", "snare", "hat", "percussion", "other", "uncertain")
FIELDS = ["dataset","track","event_id","time_seconds","window_start_seconds","window_end_seconds","candidate_sources","model_arms","mix_path","kick_stem_path","bass_stem_paths","annotation_label","decision","reviewer","reviewed_at_utc","notes"]

def event_id(track: str, stamp: float, quantum_ms: int) -> str:
    return hashlib.sha1(f"{track}|{round(stamp*1000/quantum_ms)}".encode()).hexdigest()[:12]

def load_csv(path: Path):
    if not path.exists(): return []
    with path.open(newline="", encoding="utf-8") as f: return list(csv.DictReader(f))

def bass_onsets(path: Path, cap: int):
    import librosa, numpy as np
    audio, sr = librosa.load(str(path), sr=None, mono=True)
    if not audio.size: return []
    hop=128
    env=librosa.onset.onset_strength(y=audio,sr=sr,hop_length=hop)
    if not env.size or float(np.max(env))<=0: return []
    peaks=librosa.util.peak_pick(env,pre_max=2,post_max=2,pre_avg=4,post_avg=4,delta=max(float(np.max(env))*0.10,0.025),wait=max(1,int(0.075*sr/hop)))
    return [float(x) for x in librosa.frames_to_time(peaks[:cap],sr=sr,hop_length=hop)]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest-root",type=Path,required=True); p.add_argument("--comparison-dir",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True); p.add_argument("--merge-ms",type=int,default=35); p.add_argument("--bass-onset-cap",type=int,default=500)
    a=p.parse_args()
    manifest=json.loads((a.manifest_root/"onair-manifest.json").read_text(encoding="utf-8"))
    items={x["track"]:x for x in manifest}
    events=load_csv(a.comparison_dir/"real-song-events.csv")
    grouped: dict[tuple[str,int],dict[str,Any]]={}
    def add(track,stamp,source,arm=""):
        item=items.get(track,{})
        key=(track,round(stamp*1000/a.merge_ms))
        row=grouped.setdefault(key,{"dataset":item.get("dataset","OnAir Music Dataset V4"),"track":track,"event_id":event_id(track,stamp,a.merge_ms),"time_seconds":f"{stamp:.6f}","window_start_seconds":f"{max(0,stamp-.18):.6f}","window_end_seconds":f"{stamp+.32:.6f}","candidate_sources":set(),"model_arms":set(),"mix_path":item.get("mix_path") or "","kick_stem_path":item.get("kick_stem_path") or "","bass_stem_paths":";".join(s.get("path","") for s in item.get("bass_stem_paths",[])),"annotation_label":"","decision":"","reviewer":"","reviewed_at_utc":"","notes":""})
        row["candidate_sources"].add(source)
        if arm: row["model_arms"].add(arm)
    for e in events:
        if e.get("dataset")=="OnAir Music Dataset V4" and e.get("event_status")=="prediction":
            try: add(e["track"],float(e["time_seconds"]),"model_prediction",e.get("arm",""))
            except (KeyError,ValueError): pass
    bass_count=0
    for item in manifest:
        track=item["track"]
        proposal=item.get("proposal_csv")
        for e in load_csv(Path(proposal)) if proposal else []:
            try: add(track,float(e["time_seconds"]),"isolated_kick_stem_onset_proposal")
            except (KeyError,ValueError): pass
        for stem in item.get("bass_stem_paths",[]):
            path=Path(stem["path"])
            if not path.is_file(): continue
            mix_d=float(item.get("mix_audio_metadata",{}).get("duration_seconds",0)); stem_d=float(stem.get("duration_seconds",0))
            if mix_d and stem_d and abs(mix_d-stem_d)>.10: continue
            for stamp in bass_onsets(path,a.bass_onset_cap):
                add(track,stamp,"bass_stem_transient_proposal"); bass_count+=1
    rows=[]
    for row in grouped.values():
        row["candidate_sources"]=";".join(sorted(row["candidate_sources"])); row["model_arms"]=";".join(sorted(row["model_arms"])); rows.append(row)
    rows.sort(key=lambda x:(x["track"],float(x["time_seconds"])))
    a.output.mkdir(parents=True,exist_ok=True)
    with (a.output/"kick-human-review.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    guide=f"""# Kick / bass human review queue

This file contains proposals, not ground truth. No instrument label has been assigned automatically.

1. Listen to the full mix around each row's review window.
2. Listen to the listed isolated stem at the same time. Confirm stem/mix alignment.
3. Fill annotation_label with one of: {", ".join(LABELS)}.
4. Set decision to accept only when the event and class are confirmed; use reject for a false event or uncertain when evidence is insufficient.
5. Fill reviewer, reviewed_at_utc (ISO-8601 UTC), and notes. Add missed kicks as new rows using candidate_sources=manual_added_event.
6. A bass-stem transient is not automatically bass guitar or 808: listen for the source and whether a real kick is simultaneous.

Tracks: {len(items)}
Unique clustered events: {len(rows)}
Bass-stem onset proposals: {bass_count}
All annotation_label and decision fields are blank. Source licence and checksums are in onair-manifest.json. Respect OnAir CC BY-SA 4.0 terms.
"""
    (a.output/"README-review.md").write_text(guide,encoding="utf-8")
    (a.output/"review-summary.json").write_text(json.dumps({"tracks":len(items),"candidate_events":len(rows),"bass_stem_transient_proposals":bass_count,"merge_ms":a.merge_ms,"labels":list(LABELS),"status":"unreviewed_proposals_only"},indent=2),encoding="utf-8")
    print(json.dumps({"candidate_events":len(rows),"bass_stem_transient_proposals":bass_count,"csv":str(a.output/"kick-human-review.csv")},indent=2))
    return 0
if __name__=="__main__": raise SystemExit(main())
