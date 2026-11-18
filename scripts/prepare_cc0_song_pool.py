#!/usr/bin/env python3
"""Discover and screen CC0 full-song candidates from SoundSafari.

Filename genre matches are discovery hints only. FFprobe/FFmpeg provide a
technical audio screen (duration, level, silence and clipping); they do not
verify musical genre, instrument presence, or per-track copyright ownership.
Every candidate remains subject to source-provenance and human audio review.
"""
from __future__ import annotations
import argparse, hashlib, json, random, re, subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import requests

API="https://api.github.com/repos/SoundSafari/CC0-1.0-Music"
RAW="https://raw.githubusercontent.com/SoundSafari/CC0-1.0-Music"
GENRES={
 "rock":("rock","punk","metal","grunge","alternative"),
 "funk":("funk","groove","soul"),
 "jazz":("jazz","swing","bebop","big band"),
 "blues":("blues","boogie"),
 "hip_hop":("hip hop","hip-hop","hiphop","rap","beat tape"),
 "electronic":("electronic","electronica","techno","house","trance","synthwave","electro","edm"),
 "drum_and_bass":("drum and bass","drum & bass","dnb","jungle","breakbeat"),
 "reggae":("reggae","dub","ska"),
 "disco":("disco","nu disco"),
 "country_folk":("country","folk","bluegrass","americana"),
 "pop":("pop","indie pop","dance pop"),
 "latin":("latin","salsa","bossa","reggaeton"),
}
AUDIO=re.compile(r"\.(mp3|wav|flac|ogg|m4a)$",re.I)

def raw_download_url(commit: str, repository_path: str) -> str:
 """Build a commit-pinned raw URL (the commit segment is required by GitHub)."""
 return f"{RAW}/{commit}/{quote(repository_path,safe='/')}"


def screen_duration(duration, minimum=60.0):
 if duration is None: return "metadata_probe_failed"
 if duration < minimum: return "too_short_for_full_song_benchmark"
 return "full_song_length_pass"

def screen_audio(path: Path, duration: float | None) -> dict:
 """Non-destructive technical flags; never treats these as musical labels."""
 cmd=["ffmpeg","-hide_banner","-nostats","-i",str(path),"-af",
      "silencedetect=noise=-55dB:d=1,astats=metadata=0:reset=0","-f","null","-"]
 run=subprocess.run(cmd,capture_output=True,text=True)
 log=run.stderr
 def metric(pattern):
  match=re.search(pattern,log,re.I)
  if not match:return None
  try:return float(match.group(1))
  except ValueError:return None
 peak=metric(r"Peak level dB:\s*(-?inf|-?[0-9.]+)")
 rms=metric(r"RMS level dB:\s*(-?inf|-?[0-9.]+)")
 silences=[float(x) for x in re.findall(r"silence_duration:\s*([0-9.]+)",log)]
 silence_seconds=sum(silences)
 ratio=(silence_seconds/duration) if duration and duration>0 else None
 flags=[]
 if run.returncode!=0: flags.append("ffmpeg_analysis_failed")
 if peak is None or rms is None: flags.append("level_metrics_unavailable")
 if peak is not None and peak>=-0.1: flags.append("possible_clipping_or_hot_master")
 if rms is not None and rms < -45: flags.append("very_low_average_level")
 if ratio is not None and ratio>0.35: flags.append("high_silence_ratio")
 return {"analysis_tool":"ffmpeg_astats_silencedetect","analysis_ok":run.returncode==0,
         "peak_dbfs":peak,"rms_dbfs":rms,"detected_silence_seconds":round(silence_seconds,3),
         "detected_silence_ratio":round(ratio,4) if ratio is not None else None,
         "flags":flags,"status":"technical_review" if flags else "technical_screen_pass"}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--output",type=Path,required=True); p.add_argument("--max-per-genre",type=int,default=10)
 p.add_argument("--max-total",type=int,default=120); p.add_argument("--max-file-mb",type=float,default=30)
 p.add_argument("--seed",type=int,default=20261118); p.add_argument("--genres",nargs="*",default=list(GENRES)); p.add_argument("--min-duration-seconds",type=float,default=60.0)
 a=p.parse_args()
 sess=requests.Session(); sess.headers["User-Agent"]="DrumAI-Studio-CC0-dataset-builder"
 response=sess.get(API+"/git/trees/main?recursive=1",timeout=90); response.raise_for_status()
 tree=response.json(); commit=tree["sha"]
 blobs=[x for x in tree.get("tree",[]) if x.get("type")=="blob" and AUDIO.search(x["path"]) and x.get("size",0)<=a.max_file_mb*1024*1024]
 rng=random.Random(a.seed); selected=[]; used=set(); counts={}
 for genre in a.genres:
  if genre not in GENRES: continue
  terms=GENRES[genre]
  candidates=[x for x in blobs if any(t in x["path"].lower().replace("_"," ").replace("-"," ") for t in terms) and x["path"] not in used]
  rng.shuffle(candidates); picks=candidates[:a.max_per_genre]
  for item in picks: selected.append({"genre_bucket":genre,**item}); used.add(item["path"])
  counts[genre]={"available_filename_matches":len(candidates),"selected":len(picks)}
 selected=selected[:a.max_total]
 a.output.mkdir(parents=True,exist_ok=True); manifest=[]
 for n,item in enumerate(selected,1):
  rel=item["path"]; dest=a.output/"audio"/rel; dest.parent.mkdir(parents=True,exist_ok=True)
  url=raw_download_url(commit,rel); status="downloaded"
  try:
   if not dest.exists():
    with sess.get(url,stream=True,timeout=(30,180)) as r:
     r.raise_for_status()
     with dest.open("wb") as f:
      for chunk in r.iter_content(1024*1024):
       if chunk:f.write(chunk)
   digest=hashlib.sha256(dest.read_bytes()).hexdigest(); size=dest.stat().st_size
  except Exception as exc:
   status="download_failed"; digest=""; size=0; error=str(exc)
  duration=None; duration_screen="metadata_probe_failed"; technical=None
  if status=="downloaded":
   probe=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(dest)],capture_output=True,text=True)
   if probe.returncode==0:
    try: duration=float(probe.stdout.strip()); duration_screen=screen_duration(duration,a.min_duration_seconds)
    except ValueError: duration_screen="invalid_duration"
   technical=screen_audio(dest,duration)
  record={"dataset":"SoundSafari CC0-1.0-Music","dataset_commit":commit,"repository_path":rel,"blob_sha":item["sha"],"genre_bucket":item["genre_bucket"],"genre_match_is_discovery_hint_only":True,"source_url":f"https://github.com/SoundSafari/CC0-1.0-Music/blob/{commit}/{quote(rel,safe='/')}","license":"CC0 1.0 (repository-declared; retain source provenance and honour takedown requests)","license_verified_per_track":False,"download_url":url,"local_path":str(dest) if status=="downloaded" else None,"sha256":digest,"bytes":size,"duration_seconds":duration,"full_song_length_screening":duration_screen,"technical_audio_screening":technical,"eligible_for_full_song_review":status=="downloaded" and duration is not None and duration>=a.min_duration_seconds,"status":status,"audio_screening":"pending_human_genre_and_instrument_review"}
  if status!="downloaded":record["error"]=error
  manifest.append(record)
  # Persist after every candidate so a late download/probe failure never discards
  # the provenance and screening results for files already processed.
  manifest_doc={"created_at_utc":datetime.now(timezone.utc).isoformat(),"dataset_commit":commit,"license_notice":"Repository-level CC0 declaration is discovery evidence, not a substitute for per-track provenance review. No track is assumed to contain drums or bass. Technical audio flags are not musical labels.","genre_counts":counts,"tracks":manifest}
  temp_manifest=a.output/"cc0-song-pool-manifest.json.tmp"
  temp_manifest.write_text(json.dumps(manifest_doc,indent=2,ensure_ascii=False),encoding="utf-8")
  temp_manifest.replace(a.output/"cc0-song-pool-manifest.json")
  print(f"[{n}/{len(selected)}] {item['genre_bucket']} {rel} {status} {duration_screen}",flush=True)
 print(json.dumps({"selected":len(selected),"downloaded":sum(x["status"]=="downloaded" for x in manifest),"full_song_length_pass":sum(x.get("eligible_for_full_song_review",False) for x in manifest),"technical_screen_pass":sum(x.get("technical_audio_screening",{}).get("status")=="technical_screen_pass" for x in manifest),"genre_counts":counts,"manifest":str(a.output/"cc0-song-pool-manifest.json")},indent=2))
if __name__=="__main__":main()
