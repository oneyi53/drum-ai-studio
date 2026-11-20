import importlib.util
from pathlib import Path

p=Path(__file__).with_name("discover_sound_atlas_stems.py")
spec=importlib.util.spec_from_file_location("sound_atlas_discovery",p)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_stem_names_are_normalized():
    assert m.classify_stem("Drums")=="drums"
    assert m.classify_stem("bass")=="bass"
    assert m.classify_stem("Synths & Pads")=="synthspads"

def test_only_tracks_with_both_drum_and_bass_layers_are_candidates():
    index={"tracks":{
        "song-a":{"dur":180,"stems":[{"k":"drums","f":"a.webm"},{"k":"bass","f":"b.webm"}]},
        "song-b":{"dur":120,"stems":[{"k":"drums","f":"c.webm"}]},
        "song-c":{"dur":90,"stems":[{"k":"bass","f":"d.webm"}]},
    }}
    rows=m.build_candidates(index,10)
    assert [x["track_id"] for x in rows]==["song-a"]
    assert rows[0]["kick_isolated"] is False
    assert rows[0]["license_verified_per_track"] is False
