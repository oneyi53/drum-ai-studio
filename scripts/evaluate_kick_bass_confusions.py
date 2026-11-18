#!/usr/bin/env python3
"""Score reviewed kick misses and bass/808-to-kick confusions separately."""
from __future__ import annotations
import argparse, csv, json
from collections import defaultdict
from pathlib import Path

KICK="kick"
BASS={"bass_guitar","bass_synth_808"}

def read_rows(path: Path):
    with path.open(newline="",encoding="utf-8") as f:
        return list(csv.DictReader(f))

def match_events(references, predictions, tolerance):
    refs=sorted(references,key=lambda x:x["time"])
    preds=sorted(predictions,key=lambda x:x["time"])
    used=set(); matches=[]
    for ref in refs:
        options=[(abs(pred["time"]-ref["time"]),i,pred) for i,pred in enumerate(preds)
                 if i not in used and abs(pred["time"]-ref["time"])<=tolerance]
        if options:
            _,i,pred=min(options,key=lambda x:x[0]); used.add(i); matches.append((ref,pred))
    return matches, len(preds)-len(used)

def evaluate(annotations, predictions, tolerance):
    refs=defaultdict(list); preds=defaultdict(list)
    for row in annotations:
        if row.get("decision","").strip().lower()!="accept": continue
        label=row.get("annotation_label","").strip().lower()
        if label not in {KICK,*BASS}: continue
        try: stamp=float(row["time_seconds"])
        except (KeyError,ValueError): continue
        refs[row.get("track","")].append({"time":stamp,"label":label})
    for row in predictions:
        if row.get("event_status")!="prediction": continue
        try: stamp=float(row["time_seconds"])
        except (KeyError,ValueError): continue
        preds[(row.get("track",""),row.get("arm",""))].append({"time":stamp})
    arms=sorted({arm for _,arm in preds})
    tracks=sorted(refs)
    report={"protocol":{"tolerance_ms":tolerance*1000,"only_human_accepted_annotations":True,
             "unmatched_predictions_are_not_assumed_to_be_bass":True},"arms":{}}
    for arm in arms:
        totals={"kick_reference_events":0,"kick_matched":0,"kick_missed":0,
                "bass_guitar_reference_events":0,"bass_guitar_confused_as_kick":0,
                "bass_synth_808_reference_events":0,"bass_synth_808_confused_as_kick":0,
                "unmatched_kick_predictions":0}
        per_track={}
        for track in tracks:
            track_refs=refs[track]
            track_preds=preds.get((track,arm),[])
            matches,unmatched=match_events(track_refs,track_preds,tolerance)
            counts={"kick_reference_events":sum(x["label"]==KICK for x in track_refs),
                    "kick_matched":sum(x["label"]==KICK for x,_ in matches),
                    "bass_guitar_reference_events":sum(x["label"]=="bass_guitar" for x in track_refs),
                    "bass_guitar_confused_as_kick":sum(x["label"]=="bass_guitar" for x,_ in matches),
                    "bass_synth_808_reference_events":sum(x["label"]=="bass_synth_808" for x in track_refs),
                    "bass_synth_808_confused_as_kick":sum(x["label"]=="bass_synth_808" for x,_ in matches),
                    "unmatched_kick_predictions":unmatched}
            counts["kick_missed"]=counts["kick_reference_events"]-counts["kick_matched"]
            per_track[track]=counts
            for key,value in counts.items(): totals[key]+=value
        totals["kick_recall"]=totals["kick_matched"]/totals["kick_reference_events"] if totals["kick_reference_events"] else None
        totals["bass_guitar_confusion_rate"]=totals["bass_guitar_confused_as_kick"]/totals["bass_guitar_reference_events"] if totals["bass_guitar_reference_events"] else None
        totals["bass_synth_808_confusion_rate"]=totals["bass_synth_808_confused_as_kick"]/totals["bass_synth_808_reference_events"] if totals["bass_synth_808_reference_events"] else None
        report["arms"][arm]={"overall":totals,"by_track":per_track}
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--annotations",type=Path,nargs="+",required=True)
    p.add_argument("--predictions",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--tolerance-ms",type=float,default=50)
    a=p.parse_args()
    annotations=[row for path in a.annotations for row in read_rows(path)]
    predictions=read_rows(a.predictions)
    result=evaluate(annotations,predictions,a.tolerance_ms/1000)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(result,indent=2,ensure_ascii=False))
if __name__=="__main__": main()
