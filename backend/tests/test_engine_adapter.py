from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import mido
import numpy as np
import pytest

from app import engine_adapter
from app.drum_events import DrumEvent, DrumInstrument, DrumPerformance
from app.engine_adapter import KickClassificationConfig


def _sine_signal(freq_hz: float, seconds: float = 1.0, sample_rate: int = 44100) -> np.ndarray:
    t = np.arange(int(seconds * sample_rate), dtype=np.float64) / sample_rate
    return np.sin(2 * np.pi * freq_hz * t).astype(np.float32)


def _band_magnitude(signal: np.ndarray, freq_hz: float, sample_rate: int = 44100) -> float:
    spectrum = np.abs(np.fft.rfft(signal.astype(np.float64)))
    return float(spectrum[round(freq_hz * len(signal) / sample_rate)])


def _write_percussion_midi(path: Path) -> None:
    midi = mido.MidiFile()
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.Message("note_on", channel=9, note=36, velocity=101, time=0))
    track.append(mido.MetaMessage("end_of_track", time=480))
    midi.save(path)


def _fake_extract_drum_stem(stem_path: Path, calls: dict):
    """Fake Demucs: record the separated input, return an existing stem."""
    stem_path.write_bytes(b"fake drums stem")

    def extract(audio_path, output_dir=None):
        calls["stem_input"] = audio_path
        calls["stem_output_dir"] = output_dir
        return str(stem_path)

    return extract


def _fake_engine_namespace(transcribe, stem_path: Path, calls: dict):
    """Fake ``drumscript`` module: transcribe + stem splitter + thresholds."""
    return SimpleNamespace(
        KICK_LFER_MIN=0.32,
        KICK_FREQ_MIN=40.0,
        KICK_FREQ_MAX=140.0,
        transcribe=transcribe,
        extract_drum_stem=_fake_extract_drum_stem(stem_path, calls),
    )


def _write_midi_with_notes(path: Path, notes) -> None:
    """Write a percussion MIDI with (time_seconds, gm_note, velocity) hits.

    Default tempo (120 BPM, 480 ticks/beat) so 1 s == 960 ticks.
    """
    midi = mido.MidiFile()
    track = mido.MidiTrack()
    midi.tracks.append(track)
    previous_tick = 0
    for time_seconds, note, velocity in sorted(notes):
        tick = round(time_seconds * 960)
        track.append(
            mido.Message(
                "note_on",
                channel=9,
                note=note,
                velocity=velocity,
                time=tick - previous_tick,
            )
        )
        previous_tick = tick
    track.append(mido.MetaMessage("end_of_track", time=480))
    midi.save(path)


def test_engine_adapter_separates_raw_mix_and_transcribes_stem(tmp_path, monkeypatch):
    """Phase 1 reorder: Demucs on the raw mix, transcribe on the stem.

    transcribe must run with full_song=False (no second separation, no
    htdemucs/ dump in the worker directory), and the stem splitter must
    receive the raw source — never an EQ'd file.
    """
    calls = {}

    def fake_transcribe(audio_path, **kwargs):
        calls["audio_path"] = audio_path
        calls.update(kwargs)
        midi_path = Path(audio_path).with_suffix(".mid")
        _write_percussion_midi(midi_path)
        return {"midi_path": str(midi_path)}

    monkeypatch.setattr(
        engine_adapter.importlib,
        "import_module",
        lambda name: _fake_engine_namespace(fake_transcribe, tmp_path / "drums.wav", calls),
    )
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 4.0)
    monkeypatch.chdir(tmp_path)

    source = tmp_path / "source.wav"
    source.write_bytes(b"fake audio")
    output_dir = tmp_path / "output"
    engine = engine_adapter.DrumScriptEngine(
        kick_config=KickClassificationConfig(eq_preprocessing=False)
    )
    performance, midi_path = engine.analyze(source, output_dir)

    assert calls["full_song"] is False
    assert calls["midi_only"] is True
    assert calls["verbose"] is False
    # Demucs ran on the raw source copy (name "source.wav"), inside a
    # work dir (output_dir given, so nothing lands in the CWD).
    assert Path(calls["stem_input"]).name == "source.wav"
    assert calls["stem_output_dir"] is not None
    assert not (tmp_path / "htdemucs").exists()
    # With EQ off, transcribe gets the unmodified drums stem.
    assert Path(calls["audio_path"]).name == "drums.wav"
    assert performance.duration_seconds >= 4.0
    assert performance.events[0].instrument == DrumInstrument.KICK
    assert performance.events[0].velocity == 101
    assert performance.events[0].source == "imported"
    assert midi_path == output_dir / "performance.mid"
    assert midi_path.is_file()


def test_engine_adapter_fails_clearly_when_engine_is_not_installed(tmp_path, monkeypatch):
    def missing_engine(name):
        raise ImportError(name)

    monkeypatch.setattr(engine_adapter.importlib, "import_module", missing_engine)
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 1.0)

    with pytest.raises(engine_adapter.EngineUnavailableError, match="not installed"):
        engine_adapter.DrumScriptEngine().analyze(source, tmp_path / "out")


def test_engine_adapter_rejects_missing_midi_output(tmp_path, monkeypatch):
    monkeypatch.setattr(
        engine_adapter.importlib,
        "import_module",
        lambda name: _fake_engine_namespace(lambda *args, **kwargs: {}, tmp_path / "drums.wav", {}),
    )
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 1.0)
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")

    with pytest.raises(engine_adapter.EngineOutputError, match="no MIDI path"):
        engine = engine_adapter.DrumScriptEngine(
            kick_config=KickClassificationConfig(eq_preprocessing=False)
        )
        engine.analyze(source, tmp_path / "out")


def test_kick_config_default_is_measured_gate_not_upstream():
    config = KickClassificationConfig()
    assert not config.is_upstream_default
    assert config.lfer_min == 0.10
    assert config.peak_freq_min_hz == 40.0
    assert config.peak_freq_max_hz == 140.0


def test_kick_config_explicit_upstream_values_are_stock():
    config = KickClassificationConfig(lfer_min=0.32, peak_freq_min_hz=40.0, peak_freq_max_hz=140.0)
    assert config.is_upstream_default


@pytest.mark.parametrize(
    "kwargs",
    [
        {"lfer_min": -0.01},
        {"lfer_min": 1.01},
        {"peak_freq_min_hz": 0.0, "peak_freq_max_hz": 140.0},
        {"peak_freq_min_hz": 140.0, "peak_freq_max_hz": 140.0},
        {"peak_freq_min_hz": 200.0, "peak_freq_max_hz": 140.0},
    ],
)
def test_kick_config_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        KickClassificationConfig(**kwargs)


def test_engine_adapter_applies_custom_kick_thresholds_and_restores(tmp_path, monkeypatch):
    seen = {}

    def fake_transcribe(audio_path, **kwargs):
        seen["lfer_min"] = fake.KICK_LFER_MIN
        seen["freq_min"] = fake.KICK_FREQ_MIN
        seen["freq_max"] = fake.KICK_FREQ_MAX
        midi_path = Path(audio_path).with_suffix(".mid")
        _write_percussion_midi(midi_path)
        return {"midi_path": str(midi_path)}

    fake = _fake_engine_namespace(fake_transcribe, tmp_path / "drums.wav", {})
    monkeypatch.setattr(engine_adapter.importlib, "import_module", lambda name: fake)
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 4.0)

    source = tmp_path / "source.wav"
    source.write_bytes(b"fake audio")
    engine = engine_adapter.DrumScriptEngine(
        kick_config=KickClassificationConfig(
            lfer_min=0.15, peak_freq_min_hz=40.0, peak_freq_max_hz=140.0,
            eq_preprocessing=False,
        )
    )
    engine.analyze(source, tmp_path / "output")

    assert seen == {"lfer_min": 0.15, "freq_min": 40.0, "freq_max": 140.0}
    assert fake.KICK_LFER_MIN == 0.32
    assert fake.KICK_FREQ_MIN == 40.0
    assert fake.KICK_FREQ_MAX == 140.0


def test_engine_adapter_default_config_applies_measured_gate(tmp_path, monkeypatch):
    seen = {}

    def fake_transcribe(audio_path, **kwargs):
        seen["lfer_min"] = fake.KICK_LFER_MIN
        midi_path = Path(audio_path).with_suffix(".mid")
        _write_percussion_midi(midi_path)
        return {"midi_path": str(midi_path)}

    fake = _fake_engine_namespace(fake_transcribe, tmp_path / "drums.wav", {})
    monkeypatch.setattr(engine_adapter.importlib, "import_module", lambda name: fake)
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 4.0)

    source = tmp_path / "source.wav"
    source.write_bytes(b"fake audio")
    engine = engine_adapter.DrumScriptEngine(
        kick_config=KickClassificationConfig(eq_preprocessing=False)
    )
    engine.analyze(source, tmp_path / "output")

    assert seen == {"lfer_min": 0.10}
    assert fake.KICK_LFER_MIN == 0.32


def test_engine_adapter_upstream_config_does_not_touch_thresholds(tmp_path, monkeypatch):
    def fake_transcribe(audio_path, **kwargs):
        midi_path = Path(audio_path).with_suffix(".mid")
        _write_percussion_midi(midi_path)
        return {"midi_path": str(midi_path)}

    fake = _fake_engine_namespace(fake_transcribe, tmp_path / "drums.wav", {})
    monkeypatch.setattr(engine_adapter.importlib, "import_module", lambda name: fake)
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 4.0)

    source = tmp_path / "source.wav"
    source.write_bytes(b"fake audio")
    engine = engine_adapter.DrumScriptEngine(
        kick_config=KickClassificationConfig(lfer_min=0.32, eq_preprocessing=False)
    )
    engine.analyze(source, tmp_path / "output")

    assert fake.KICK_LFER_MIN == 0.32
    assert fake.KICK_FREQ_MIN == 40.0
    assert fake.KICK_FREQ_MAX == 140.0


def test_engine_adapter_fails_closed_when_threshold_override_unsupported(tmp_path, monkeypatch):
    # Fake engine without the upstream threshold attributes: a non-default
    # config must fail loudly instead of silently running unmodified.
    # The stem splitter is present (separation runs before the override),
    # so the failure must come from the threshold check itself.
    monkeypatch.setattr(
        engine_adapter.importlib,
        "import_module",
        lambda name: SimpleNamespace(
            transcribe=lambda *args, **kwargs: {},
            extract_drum_stem=_fake_extract_drum_stem(tmp_path / "drums.wav", {}),
        ),
    )
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 1.0)
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")

    engine = engine_adapter.DrumScriptEngine(
        kick_config=KickClassificationConfig(lfer_min=0.15, eq_preprocessing=False)
    )
    with pytest.raises(engine_adapter.EngineUnavailableError, match="does not expose"):
        engine.analyze(source, tmp_path / "out")


def test_kick_eq_boosts_low_frequencies_and_attenuates_subsonic():
    sample_rate = 44100
    signal = (
        _sine_signal(60.0, sample_rate=sample_rate)
        + _sine_signal(1000.0, sample_rate=sample_rate)
        + _sine_signal(10.0, sample_rate=sample_rate)
    )
    filtered = engine_adapter._apply_kick_eq(signal, sample_rate)
    assert filtered.dtype == np.float32
    assert filtered.shape == signal.shape
    # +6 dB shelf below 120 Hz roughly doubles the 60 Hz component, the
    # 30 Hz high-pass removes most of the 10 Hz component, 1 kHz is untouched.
    assert 1.7 < _band_magnitude(filtered, 60.0) / _band_magnitude(signal, 60.0) < 2.2
    assert _band_magnitude(filtered, 10.0) / _band_magnitude(signal, 10.0) < 0.3
    assert 0.9 < _band_magnitude(filtered, 1000.0) / _band_magnitude(signal, 1000.0) < 1.1


def test_kick_eq_empty_input_returns_empty():
    filtered = engine_adapter._apply_kick_eq(np.array([], dtype=np.float32), 44100)
    assert filtered.dtype == np.float32
    assert filtered.size == 0


def test_kick_eq_rejects_non_mono_input():
    stereo = np.zeros((2, 44100), dtype=np.float32)
    with pytest.raises(engine_adapter.EngineUnavailableError, match="mono"):
        engine_adapter._apply_kick_eq(stereo, 44100)


def _eq_import_dispatcher(monkeypatch, fake_engine, fake_load_audio, fail_names=()):
    """Fake drumscript loader/constants; delegate everything else (scipy,
    numpy) to the real import machinery unless listed in fail_names."""
    real_import = importlib.import_module

    def fake_import(name):
        if name in fail_names:
            raise ImportError(name)
        if name == "drumscript":
            return fake_engine
        if name == "drumscript.drum_classifier.classify":
            return fake_engine
        if name == "drumscript.audio_processor.stem_splitter":
            return fake_engine
        if name == "drumscript.audio_processor.audio_loader":
            return SimpleNamespace(load_audio=fake_load_audio)
        if name == "drumscript.notation_generator.constants":
            return SimpleNamespace(SAMPLE_RATE=44100)
        return real_import(name)

    monkeypatch.setattr(engine_adapter.importlib, "import_module", fake_import)


def _eq_fake_engine(transcribe, stem_path: Path, calls: dict):
    return SimpleNamespace(
        KICK_LFER_MIN=0.32,
        KICK_FREQ_MIN=40.0,
        KICK_FREQ_MAX=140.0,
        transcribe=transcribe,
        extract_drum_stem=_fake_extract_drum_stem(stem_path, calls),
    )


def test_engine_adapter_default_config_applies_eq_to_drums_stem(tmp_path, monkeypatch):
    """Phase 1 reorder: the EQ goes on the separated drums stem, never on
    the mix — Demucs sees the raw source, transcribe sees drums-eq.wav."""
    seen = {}

    def fake_transcribe(audio_path, **kwargs):
        seen["audio_path"] = audio_path
        seen["lfer_min"] = fake.KICK_LFER_MIN
        wav_path = Path(audio_path)
        assert wav_path.name == "drums-eq.wav"
        assert wav_path.is_file()
        from scipy.io import wavfile

        rate, data = wavfile.read(str(wav_path))
        assert rate == 44100
        assert data.size > 0
        midi_path = wav_path.with_suffix(".mid")
        _write_percussion_midi(midi_path)
        return {"midi_path": str(midi_path)}

    fake = _eq_fake_engine(fake_transcribe, tmp_path / "drums.wav", seen)

    def fake_load_audio(path, sr=None):
        seen["load_audio_called"] = True
        seen["load_audio_path"] = path
        return _sine_signal(60.0, seconds=0.5), 44100

    _eq_import_dispatcher(monkeypatch, fake, fake_load_audio)
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 4.0)

    source = tmp_path / "source.wav"
    source.write_bytes(b"fake audio")
    engine_adapter.DrumScriptEngine().analyze(source, tmp_path / "output")

    assert seen["load_audio_called"] is True
    # The EQ loaded the drums stem (not the mix).
    assert Path(seen["load_audio_path"]).name == "drums.wav"
    # Demucs separated the raw source (not an EQ'd file).
    assert Path(seen["stem_input"]).name == "source.wav"
    assert seen["stem_output_dir"] is not None
    assert seen["lfer_min"] == 0.10
    assert Path(seen["audio_path"]).name == "drums-eq.wav"


def test_engine_adapter_eq_disabled_transcribes_unmodified_drums_stem(tmp_path, monkeypatch):
    seen = {}

    def fake_transcribe(audio_path, **kwargs):
        seen["audio_path"] = audio_path
        midi_path = Path(audio_path).with_suffix(".mid")
        _write_percussion_midi(midi_path)
        return {"midi_path": str(midi_path)}

    def fake_load_audio(path, sr=None):
        raise AssertionError("load_audio must not be called when EQ is disabled")

    _eq_import_dispatcher(
        monkeypatch,
        _eq_fake_engine(fake_transcribe, tmp_path / "drums.wav", seen),
        fake_load_audio,
    )
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 4.0)

    source = tmp_path / "source.wav"
    source.write_bytes(b"fake audio")
    engine = engine_adapter.DrumScriptEngine(
        kick_config=KickClassificationConfig(eq_preprocessing=False)
    )
    engine.analyze(source, tmp_path / "output")

    # With EQ off, transcribe gets the unmodified drums stem — never the mix.
    assert Path(seen["audio_path"]).name == "drums.wav"
    assert Path(seen["stem_input"]).name == "source.wav"


def test_engine_adapter_eq_fails_closed_when_loader_missing(tmp_path, monkeypatch):
    def never_transcribe(*args, **kwargs):
        raise AssertionError("transcribe must not run when EQ preparation fails")

    _eq_import_dispatcher(
        monkeypatch,
        _eq_fake_engine(never_transcribe, tmp_path / "drums.wav", {}),
        lambda *args, **kwargs: None,
        fail_names={"drumscript.audio_processor.audio_loader"},
    )
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 1.0)
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")

    with pytest.raises(engine_adapter.EngineUnavailableError, match="drumscript"):
        engine_adapter.DrumScriptEngine().analyze(source, tmp_path / "out")


def test_engine_adapter_eq_fails_closed_when_scipy_missing(tmp_path, monkeypatch):
    def never_transcribe(*args, **kwargs):
        raise AssertionError("transcribe must not run when EQ preparation fails")

    def fake_load_audio(path, sr=None):
        return _sine_signal(60.0, seconds=0.5), 44100

    _eq_import_dispatcher(
        monkeypatch,
        _eq_fake_engine(never_transcribe, tmp_path / "drums.wav", {}),
        fake_load_audio,
        fail_names={"scipy.signal"},
    )
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 1.0)
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")

    with pytest.raises(engine_adapter.EngineUnavailableError, match="scipy"):
        engine_adapter.DrumScriptEngine().analyze(source, tmp_path / "out")


def test_kick_config_eq_preprocessing_defaults_on_and_restores_stock():
    assert KickClassificationConfig().eq_preprocessing is True
    assert KickClassificationConfig(eq_preprocessing=False).eq_preprocessing is False
    stock = KickClassificationConfig(lfer_min=0.32, eq_preprocessing=False)
    assert stock.is_upstream_default
    assert stock.eq_preprocessing is False
    with pytest.raises(TypeError):
        KickClassificationConfig(eq_preprocessing="yes")


def _write_stock_tempo_midi(path: Path) -> None:
    """Upstream-shaped MIDI: type 1, 220 tpq, set_tempo 69.8 BPM."""
    ticks_per_beat = 220
    ticks_per_second = ticks_per_beat * 69.8 / 60.0
    midi = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    conductor = mido.MidiTrack()
    conductor.append(
        mido.MetaMessage("set_tempo", tempo=round(60_000_000 / 69.8), time=0)
    )
    conductor.append(
        mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0)
    )
    conductor.append(mido.MetaMessage("end_of_track", time=1))
    midi.tracks.append(conductor)
    notes = mido.MidiTrack()
    notes.append(
        mido.Message(
            "note_on",
            channel=9,
            note=36,
            velocity=101,
            time=round(1.0 * ticks_per_second),
        )
    )
    notes.append(
        mido.Message(
            "note_on",
            channel=9,
            note=36,
            velocity=0,
            time=round(0.2 * ticks_per_second),
        )
    )
    notes.append(mido.MetaMessage("end_of_track", time=0))
    midi.tracks.append(notes)
    midi.save(path)


def _run_engine_with_tempo(monkeypatch, tmp_path, corrected_bpm):
    """Run analyze() with a fake engine and a stubbed tempo correction."""
    from app.drum_events import TempoChange

    def fake_transcribe(audio_path, **kwargs):
        midi_path = Path(audio_path).with_suffix(".mid")
        _write_stock_tempo_midi(midi_path)
        return {"midi_path": str(midi_path)}

    monkeypatch.setattr(
        engine_adapter.importlib,
        "import_module",
        lambda name: _fake_engine_namespace(fake_transcribe, tmp_path / "drums.wav", {}),
    )
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 4.0)
    monkeypatch.setattr(
        engine_adapter,
        "correct_tempo_map",
        lambda tempo_map, audio, checkpoint: (
            [TempoChange(time_seconds=0, bpm=corrected_bpm, numerator=4, denominator=4)],
            "beat_this",
        ),
    )
    source = tmp_path / "source.wav"
    source.write_bytes(b"fake audio")
    engine = engine_adapter.DrumScriptEngine(
        kick_config=KickClassificationConfig(eq_preprocessing=False)
    )
    return engine.analyze(source, tmp_path / "output")


def _exported_tempo_bpm(midi_path: Path) -> float:
    midi = mido.MidiFile(midi_path)
    tempos = [
        60_000_000 / message.tempo
        for track in midi.tracks
        for message in track
        if message.type == "set_tempo"
    ]
    assert len(tempos) == 1
    return tempos[0]


def test_engine_adapter_exports_corrected_tempo_in_midi(tmp_path, monkeypatch):
    performance, midi_path = _run_engine_with_tempo(monkeypatch, tmp_path, 142.86)
    assert performance.tempo_map[0].bpm == pytest.approx(142.86)
    assert _exported_tempo_bpm(midi_path) == pytest.approx(142.86)
    assert performance.events[0].time_seconds == pytest.approx(1.0, abs=0.01)


def test_engine_adapter_keeps_stock_tempo_when_uncorrected(tmp_path, monkeypatch):
    performance, midi_path = _run_engine_with_tempo(monkeypatch, tmp_path, 69.8)
    assert performance.tempo_map[0].bpm == pytest.approx(69.8)
    assert _exported_tempo_bpm(midi_path) == pytest.approx(69.8)
    assert performance.events[0].time_seconds == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# Phase 1 (2026-11-16): crash decay suppression + rolled-back rules.
# Measurements: ~/workspace/.ds-scratch/downstream-plan/PHASE1_IMPLEMENTATION.md
# ---------------------------------------------------------------------------


def _crash_performance(times, other=()):
    events = [
        DrumEvent(time_seconds=t, instrument=DrumInstrument.CRASH, velocity=100) for t in times
    ]
    events.extend(DrumEvent(time_seconds=t, instrument=inst, velocity=100) for t, inst in other)
    return DrumPerformance(duration_seconds=10.0, events=events, tempo_map=[])


def test_crash_decay_suppression_keeps_first_crash_in_window():
    # Crashes at 0.0, 0.5, 1.0 fall in one 1.5 s window (only 0.0 kept);
    # 2.0 opens a new window; 3.6 opens another. A snare inside a window
    # is untouched — the rule only drops crash labels.
    performance = _crash_performance(
        [0.0, 0.5, 1.0, 2.0, 3.6],
        other=[(0.5, DrumInstrument.SNARE)],
    )
    suppressed = engine_adapter.apply_crash_decay_suppression(performance)
    crashes = [e.time_seconds for e in suppressed.events if e.instrument is DrumInstrument.CRASH]
    assert crashes == [0.0, 2.0, 3.6]
    snares = [e.time_seconds for e in suppressed.events if e.instrument is DrumInstrument.SNARE]
    assert snares == [0.5]
    assert len(suppressed.events) == 4


def test_crash_decay_suppression_window_is_inclusive():
    # A crash exactly 1.5 s after a kept crash is inside the window.
    performance = _crash_performance([0.0, 1.5])
    suppressed = engine_adapter.apply_crash_decay_suppression(performance)
    assert len(suppressed.events) == 1
    # Just past the window it is a new attack and is kept.
    performance = _crash_performance([0.0, 1.5001])
    suppressed = engine_adapter.apply_crash_decay_suppression(performance)
    assert len(suppressed.events) == 2


def test_crash_decay_suppression_rejects_non_positive_window():
    performance = _crash_performance([0.0])
    with pytest.raises(ValueError, match="window_seconds"):
        engine_adapter.apply_crash_decay_suppression(performance, window_seconds=0)


def _run_engine_with_notes(monkeypatch, tmp_path, notes):
    """Run analyze() with a fake engine whose MIDI holds ``notes``.

    ``notes`` is a list of (time_seconds, GM percussion note, velocity).
    Returns (performance, midi_path).
    """

    def fake_transcribe(audio_path, **kwargs):
        midi_path = Path(audio_path).with_suffix(".mid")
        _write_midi_with_notes(midi_path, notes)
        return {"midi_path": str(midi_path)}

    monkeypatch.setattr(
        engine_adapter.importlib,
        "import_module",
        lambda name: _fake_engine_namespace(fake_transcribe, tmp_path / "drums.wav", {}),
    )
    monkeypatch.setattr(engine_adapter, "audio_duration_seconds", lambda path: 4.0)
    source = tmp_path / "source.wav"
    source.write_bytes(b"fake audio")
    engine = engine_adapter.DrumScriptEngine(
        kick_config=KickClassificationConfig(eq_preprocessing=False)
    )
    return engine.analyze(source, tmp_path / "output")


def test_engine_adapter_suppresses_crash_retriggers_end_to_end(tmp_path, monkeypatch):
    # Crashes at 0.0, 0.5 (re-trigger), 2.0 (new window) + a kick at 0.5.
    # The output performance and the written MIDI must both lose the 0.5 s
    # crash and keep everything else.
    performance, midi_path = _run_engine_with_notes(
        monkeypatch,
        tmp_path,
        [(0.0, 49, 100), (0.5, 49, 100), (0.5, 36, 100), (2.0, 49, 100)],
    )
    crashes = [e.time_seconds for e in performance.events if e.instrument is DrumInstrument.CRASH]
    assert crashes == [0.0, 2.0]
    kicks = [e.time_seconds for e in performance.events if e.instrument is DrumInstrument.KICK]
    assert kicks == [0.5]
    from app.midi_adapter import midi_to_performance

    exported = midi_to_performance(midi_path)
    exported_crashes = [
        e.time_seconds for e in exported.events if e.instrument is DrumInstrument.CRASH
    ]
    assert exported_crashes == [0.0, 2.0]


def test_engine_adapter_keeps_simultaneous_hits(tmp_path, monkeypatch):
    """One-label rule ROLLED BACK (Phase 1): simultaneous hits are the norm.

    A kick + snare + closed hihat at the same onset must all survive
    analyze() — the margin-strength argmax that would drop two of them
    broke the IDMT gate (kick F1 0.840 -> 0.746) and moved no snare count.
    """
    performance, _midi_path = _run_engine_with_notes(
        monkeypatch,
        tmp_path,
        [(1.0, 36, 100), (1.0, 38, 100), (1.0, 42, 100)],
    )
    at_one_second = sorted(
        e.instrument for e in performance.events if e.time_seconds == pytest.approx(1.0)
    )
    assert at_one_second == [
        DrumInstrument.CLOSED_HIHAT,
        DrumInstrument.KICK,
        DrumInstrument.SNARE,
    ]


def test_engine_adapter_adds_no_kicks_from_bass_channel(tmp_path, monkeypatch):
    """Kick dual-channel ROLLED BACK (Phase 1): no bass-flux kick channel.

    The performance kick set must equal the classifier's kick set exactly
    — no added kicks, no downgraded kicks. The bass-flux addition would
    have added 156-385 bogus kicks per track (measured), and the
    downgrade was a no-op.
    """
    performance, _midi_path = _run_engine_with_notes(
        monkeypatch,
        tmp_path,
        [(0.5, 36, 100), (1.0, 38, 100), (1.5, 36, 100)],
    )
    kicks = sorted(
        e.time_seconds for e in performance.events if e.instrument is DrumInstrument.KICK
    )
    assert kicks == [0.5, 1.5]
