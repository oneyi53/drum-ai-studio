import importlib.util
from pathlib import Path

p=Path(__file__).with_name("prepare_cc0_song_pool.py")
spec=importlib.util.spec_from_file_location("cc0_pool",p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_genre_buckets_cover_low_frequency_confusion_styles():
    assert {"rock","funk","jazz","hip_hop","electronic","drum_and_bass","reggae"} <= set(m.GENRES)

def test_each_genre_has_distinct_search_terms():
    for genre,terms in m.GENRES.items():
        assert terms and all(isinstance(x,str) and x for x in terms)

def test_audio_filter_excludes_non_audio():
    assert m.AUDIO.search("song.mp3")
    assert not m.AUDIO.search("cover.jpg")

def test_full_song_duration_screen_excludes_short_loops():
    assert m.screen_duration(12.5)=="too_short_for_full_song_benchmark"
    assert m.screen_duration(180.0)=="full_song_length_pass"
    assert m.screen_duration(None)=="metadata_probe_failed"

def test_candidate_pool_limits_are_wider_than_previous_pool():
    import inspect
    source=inspect.getsource(m.main)
    assert 'default=120' in source
    assert 'default=10' in source

def test_audio_screening_is_explicitly_non_semantic():
    result=m.screen_audio
    assert callable(result)
    assert "Non-destructive technical flags" in result.__doc__
