#!/usr/bin/env python3
"""Train an independently initialized multi-class event CNN from approved labels."""
from __future__ import annotations
import argparse,csv,hashlib,json,random,math
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import numpy as np

LABELS=["kick","bass_guitar","bass_synth_808","snare","hat","percussion","other"]
ALLOW={"CC0 1.0","CC BY 4.0","CC BY 3.0","CC BY 2.0"}

def load_approved(manifest_path,annotation_paths,allow_sharealike):
    data=json.loads(manifest_path.read_text(encoding="utf-8")); sources=data if isinstance(data,list) else data.get("sources",[])
    by_track={x.get("track") or x.get("title"):x for x in sources}; out=[]
    for path in annotation_paths:
        with path.open(newline="",encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("decision","").strip().lower()!="accept": continue
                label=row.get("annotation_label","").strip().lower()
                if label not in LABELS: continue
                track=row.get("track",""); src=by_track.get(track,{})
                lic=(src.get("license") or row.get("license","")).strip()
                verified = src.get("license_verified_per_track") is True or row.get("license_verified","").strip().lower() in {"1","true","yes"}
                if not verified:
                    raise ValueError(f"Per-track licence is not explicitly verified for {track!r}; repository-level declarations are insufficient.")
                if lic not in ALLOW and not (allow_sharealike and lic=="CC BY-SA 4.0"):
                    raise ValueError(f"Non-allowlisted licence {lic!r} for {track!r}; rights review required.")
                audio=row.get("mix_path") or src.get("mix_path") or src.get("file")
                if not audio or not Path(audio).is_file(): raise ValueError(f"Missing audio for {track!r}")
                try: seconds=float(row["time_seconds"])
                except (TypeError,ValueError): raise ValueError(f"Invalid time_seconds for {track!r}")
                if not math.isfinite(seconds) or seconds < 0: raise ValueError(f"Invalid time_seconds for {track!r}: {seconds}")
                expected=src.get("mix_sha256") or src.get("sha256")
                if expected and hashlib.sha256(Path(audio).read_bytes()).hexdigest()!=expected:
                    raise ValueError(f"Audio checksum mismatch for {track!r}")
                out.append({"track":track,"audio_path":str(audio),"time_seconds":seconds,"label":label,"license":lic})
    return out

def make_features(items):
    import librosa
    cache={}; feats=[]; ys=[]; groups=[]
    for x in items:
        if x["audio_path"] not in cache: cache[x["audio_path"]],_=librosa.load(x["audio_path"],sr=22050,mono=True)
        y=cache[x["audio_path"]]; center=int(x["time_seconds"]*22050); length=96*256
        if center >= len(y): raise ValueError(f"Annotation time exceeds audio duration for {x['track']!r}: {x['time_seconds']}")
        start=max(0,center-length//2); crop=y[start:start+length]
        if len(crop)<length: crop=np.pad(crop,(0,length-len(crop)))
        mel=librosa.feature.melspectrogram(y=crop,sr=22050,n_fft=1024,hop_length=256,n_mels=96,power=2)
        feat=librosa.power_to_db(mel,ref=np.max)
        if feat.shape[1]<96: feat=np.pad(feat,((0,0),(0,96-feat.shape[1])))
        feats.append(feat[:,:96].astype(np.float32)); ys.append(LABELS.index(x["label"])); groups.append(x["track"])
    return np.stack(feats),np.asarray(ys,dtype=np.int64),np.asarray(groups)

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--manifest",type=Path,required=True); p.add_argument("--annotations",type=Path,nargs="+",required=True); p.add_argument("--output",type=Path,required=True)
    p.add_argument("--epochs",type=int,default=30); p.add_argument("--batch-size",type=int,default=32); p.add_argument("--min-tracks",type=int,default=8); p.add_argument("--min-per-class",type=int,default=20); p.add_argument("--allow-sharealike",action="store_true"); p.add_argument("--seed",type=int,default=2026); a=p.parse_args()
    items=load_approved(a.manifest,a.annotations,a.allow_sharealike); counts=Counter(x["label"] for x in items); tracks=sorted({x["track"] for x in items})
    missing=[k for k in LABELS if counts[k]<a.min_per_class]
    if len(tracks)<a.min_tracks or missing: raise SystemExit(f"Insufficient reviewed data: tracks={len(tracks)}/{a.min_tracks}; counts={dict(counts)}; underrepresented={missing}.")
    class_track_counts={label:len({x["track"] for x in items if x["label"]==label}) for label in LABELS}
    split_unsafe={label:n for label,n in class_track_counts.items() if n<2}
    if split_unsafe: raise SystemExit(f"Each class must occur in at least two distinct tracks for track-held-out validation: {split_unsafe}")
    X,y,groups=make_features(items); random.seed(a.seed); shuffled=tracks[:]; random.shuffle(shuffled); val=set(shuffled[:max(1,round(len(shuffled)*.2))])
    tr=np.asarray([i for i,t in enumerate(groups) if t not in val]); va=np.asarray([i for i,t in enumerate(groups) if t in val])
    if not len(tr) or not len(va): raise SystemExit("Track-grouped split is empty.")
    train_classes=set(y[tr].tolist()); validation_classes=set(y[va].tolist())
    absent_train=[LABELS[i] for i in range(len(LABELS)) if i not in train_classes]
    absent_validation=[LABELS[i] for i in range(len(LABELS)) if i not in validation_classes]
    if absent_train or absent_validation:
        raise SystemExit(f"Track-held-out split must contain every class in both partitions; missing_train={absent_train}; missing_validation={absent_validation}. Add reviewed examples from more tracks.")
    import torch
    from torch import nn
    from torch.utils.data import DataLoader,TensorDataset
    class EventCNN(nn.Module):
        def __init__(self):
            super().__init__(); self.features=nn.Sequential(nn.Conv2d(1,16,3,padding=1),nn.BatchNorm2d(16),nn.ReLU(),nn.MaxPool2d(2),nn.Conv2d(16,32,3,padding=1),nn.BatchNorm2d(32),nn.ReLU(),nn.MaxPool2d(2),nn.Conv2d(32,64,3,padding=1),nn.ReLU(),nn.AdaptiveAvgPool2d((1,1))); self.head=nn.Linear(64,len(LABELS))
        def forward(self,x): return self.head(self.features(x).flatten(1))
    torch.manual_seed(a.seed); model=EventCNN(); ds=TensorDataset(torch.from_numpy(X[tr,None]),torch.from_numpy(y[tr])); loader=DataLoader(ds,batch_size=a.batch_size,shuffle=True)
    vx,vy=torch.from_numpy(X[va,None]),torch.from_numpy(y[va]); opt=torch.optim.AdamW(model.parameters(),lr=1e-3,weight_decay=1e-4); loss_fn=nn.CrossEntropyLoss(); history=[]
    for epoch in range(a.epochs):
        model.train(); total=0
        for xb,yb in loader:
            opt.zero_grad(); loss=loss_fn(model(xb),yb); loss.backward(); opt.step(); total+=float(loss.item())*len(yb)
        model.eval()
        with torch.no_grad(): acc=float((model(vx).argmax(1)==vy).float().mean().item())
        history.append({"epoch":epoch+1,"train_loss":total/len(ds),"track_holdout_accuracy":acc})
    model.eval()
    with torch.no_grad(): validation_predictions=model(vx).argmax(1).cpu().numpy()
    confusion=np.zeros((len(LABELS),len(LABELS)),dtype=int)
    for truth,pred in zip(y[va],validation_predictions): confusion[int(truth),int(pred)]+=1
    per_class={}
    for i,label in enumerate(LABELS):
        tp=int(confusion[i,i]); support=int(confusion[i,:].sum()); predicted=int(confusion[:,i].sum())
        precision=tp/predicted if predicted else 0.0; recall=tp/support if support else 0.0
        per_class[label]={"precision":precision,"recall":recall,"f1":2*precision*recall/(precision+recall) if precision+recall else 0.0,"support":support}
    hashes={path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in sorted({x["audio_path"] for x in items})}; licenses=sorted({x["license"] for x in items})
    a.output.parent.mkdir(parents=True,exist_ok=True)
    torch.save({"state_dict":model.state_dict(),"labels":LABELS,"feature_config":{"sample_rate":22050,"n_fft":1024,"hop_length":256,"n_mels":96,"frames":96,"window_seconds":96*256/22050},"train_tracks":sorted(set(groups[tr].tolist())),"validation_tracks":sorted(set(groups[va].tolist())),"source_licenses":licenses,"source_audio_sha256":hashes,"created_at_utc":datetime.now(timezone.utc).isoformat(),"note":"Independent initialization; no STAR/AGPL weights loaded. Experimental only; separate licence review required."},a.output)
    meta={"examples":len(items),"tracks":len(tracks),"class_counts":dict(counts),"class_track_counts":class_track_counts,"train_tracks":sorted(set(groups[tr].tolist())),"validation_tracks":sorted(set(groups[va].tolist())),"source_licenses":licenses,"validation_confusion_matrix":confusion.tolist(),"validation_per_class":per_class,"history":history,"checkpoint":str(a.output)}
    a.output.with_suffix(".json").write_text(json.dumps(meta,indent=2),encoding="utf-8"); print(json.dumps(meta,indent=2))
if __name__=="__main__": main()
