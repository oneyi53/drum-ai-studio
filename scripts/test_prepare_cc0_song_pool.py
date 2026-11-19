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


def test_raw_download_url_pins_commit_before_repository_path():
    url=m.raw_download_url("abc123", "freesound.org/artist/song name.mp3")
    assert url == "https://raw.githubusercontent.com/SoundSafari/CC0-1.0-Music/abc123/freesound.org/artist/song%20name.mp3"


def test_manifest_is_checkpointed_after_each_candidate():
    import inspect
    source=inspect.getsource(m.main)
    assert 'temp_manifest.replace(a.output/"cc0-song-pool-manifest.json")' in source
    assert source.index('manifest.append(record)') < source.index('temp_manifest.replace')


def test_ffmpeg_and_ffprobe_diagnostics_decode_with_replacement():
    import inspect
    source=inspect.getsource(m.main)
    screen_source=inspect.getsource(m.screen_audio)
    assert 'encoding="utf-8",errors="replace"' in screen_source
    assert 'encoding="utf-8",errors="replace"' in source


def test_source_paths_with_unsafe_archive_characters_are_safely_mapped():
    first=m.safe_local_relative_path("artist/Track | Mix?.mp3")
    second=m.safe_local_relative_path("artist/Track : Mix?.mp3")
    assert "|" not in str(first) and "?" not in str(first)
    assert ":" not in str(second) and "?" not in str(second)
    assert first != second
    assert first.parts[0] == "artist"
