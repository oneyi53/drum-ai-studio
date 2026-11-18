import csv, importlib.util, json
from pathlib import Path
import pytest

p=Path(__file__).with_name("train_kick_event_classifier.py")
spec=importlib.util.spec_from_file_location("kick_trainer",p)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def make_inputs(tmp_path, verified):
    audio=tmp_path/"mix.wav"; audio.write_bytes(b"test-audio")
    manifest=tmp_path/"manifest.json"
    manifest.write_text(json.dumps({"sources":[{
        "track":"track-a","license":"CC0 1.0",
        "license_verified_per_track":verified,
        "mix_path":str(audio)
    }]}),encoding="utf-8")
    annotations=tmp_path/"annotations.csv"
    with annotations.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["track","time_seconds","annotation_label","decision"])
        w.writeheader()
        w.writerow({"track":"track-a","time_seconds":"1.25","annotation_label":"kick","decision":"accept"})
    return manifest,annotations

def test_repository_level_cc0_claim_is_not_enough(tmp_path):
    manifest,annotations=make_inputs(tmp_path,False)
    with pytest.raises(ValueError,match="Per-track licence"):
        m.load_approved(manifest,[annotations],False)

def test_explicitly_verified_cc0_track_is_accepted(tmp_path):
    manifest,annotations=make_inputs(tmp_path,True)
    rows=m.load_approved(manifest,[annotations],False)
    assert len(rows)==1 and rows[0]["license"]=="CC0 1.0"

def test_unapproved_licence_is_rejected_even_when_verified(tmp_path):
    manifest,annotations=make_inputs(tmp_path,True)
    data=json.loads(manifest.read_text()); data["sources"][0]["license"]="CC BY-NC 4.0"
    manifest.write_text(json.dumps(data),encoding="utf-8")
    with pytest.raises(ValueError,match="Non-allowlisted"):
        m.load_approved(manifest,[annotations],False)


def test_first_stage_model_is_scoped_to_kick_bass_and_808():
    assert m.LABELS == ["kick", "bass_guitar", "bass_synth_808"]


def test_track_group_split_has_three_disjoint_song_partitions():
    import numpy as np
    track_ids=list("abcdefghijkl")
    groups=np.repeat(track_ids,2)
    labels=np.repeat([0,1,2]*4,2)
    tr,va,te,parts=m.split_track_groups(groups,labels,seed=7)
    assert set(parts["train"]).isdisjoint(parts["validation"])
    assert set(parts["train"]).isdisjoint(parts["test"])
    assert set(parts["validation"]).isdisjoint(parts["test"])
    assert set(labels[tr])==set(labels[va])==set(labels[te])=={0,1,2}

def test_three_way_split_rejects_class_with_only_two_tracks():
    import numpy as np
    groups=np.array(list("abcdefgh"))
    labels=np.array([0,0,0,1,1,1,2,2])
    with pytest.raises(ValueError,match="at least three distinct tracks"):
        m.split_track_groups(groups,labels)


def test_trainer_uses_three_channel_temporal_spectral_features():
    source=p.read_text(encoding="utf-8")
    assert 'np.stack((log_mel,delta,delta2),axis=0)' in source
    assert 'nn.Conv2d(3,16' in source
    assert 'torch.from_numpy(X[tr])' in source
