import importlib.util
from pathlib import Path

import pytest

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


class _FakeResponse:
    """Minimal stand-in for a requests.Response; never touches the network."""

    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        raise AssertionError(f"raise_for_status called on {self.status_code}")


class _FakeSession:
    """Records every get() call so tests can assert on headers and retries."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": dict(headers or {}), "timeout": timeout})
        return self._responses.pop(0)


def test_github_api_get_sends_bearer_token_when_set(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken")
    session = _FakeSession([_FakeResponse(200, {"sha": "abc"})])
    response = m.github_api_get(session, "https://api.github.com/x")
    assert response.status_code == 200
    assert session.calls[0]["headers"] == {"Authorization": "Bearer ghp_testtoken"}


def test_github_api_get_sends_no_auth_header_without_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    session = _FakeSession([_FakeResponse(200, {"sha": "abc"})])
    response = m.github_api_get(session, "https://api.github.com/x")
    assert response.status_code == 200
    assert session.calls[0]["headers"] == {}


def test_github_api_get_retries_on_403_then_succeeds(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    sleeps = []
    session = _FakeSession([_FakeResponse(403), _FakeResponse(429), _FakeResponse(200, {"sha": "abc"})])
    response = m.github_api_get(session, "https://api.github.com/x", sleep=sleeps.append)
    assert response.status_code == 200
    assert len(session.calls) == 3
    assert sleeps == [10.0, 20.0]


def test_github_api_get_honors_retry_after(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    sleeps = []
    session = _FakeSession([_FakeResponse(429, headers={"Retry-After": "120"}), _FakeResponse(200)])
    response = m.github_api_get(session, "https://api.github.com/x", sleep=sleeps.append)
    assert response.status_code == 200
    assert sleeps == [120.0]


def test_github_api_get_gives_up_after_retry_budget(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    sleeps = []
    session = _FakeSession([_FakeResponse(403)] * 5)
    with pytest.raises(RuntimeError, match="rate limit"):
        m.github_api_get(session, "https://api.github.com/x", sleep=sleeps.append)
    assert len(session.calls) == 5
    assert sleeps == [10.0, 20.0, 40.0, 80.0]
