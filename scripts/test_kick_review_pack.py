import importlib.util
from pathlib import Path
p=Path(__file__).with_name("build_kick_review_pack.py")
spec=importlib.util.spec_from_file_location("review_pack",p)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_event_id_is_stable_and_track_specific():
    assert m.event_id("track-a",1.001,35)==m.event_id("track-a",1.001,35)
    assert m.event_id("track-a",1.001,35)!=m.event_id("track-b",1.001,35)

def test_review_labels_cover_bass_and_drums():
    assert {"kick","bass_guitar","bass_synth_808","snare","hat","percussion","other","uncertain"}==set(m.LABELS)
