from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluate_midi import DRUMSCRIPT_DRUM_MAP, Event, evaluate, normalize_instrument


def test_perfect_match_has_perfect_metrics() -> None:
    events = [Event(0.0, "kick"), Event(0.5, "snare"), Event(1.0, "closed_hat")]
    report = evaluate(events, events, tolerance=0.05)
    assert report["overall"]["true_positives"] == 3
    assert report["overall"]["false_positives"] == 0
    assert report["overall"]["false_negatives"] == 0
    assert report["overall"]["f1"] == 1.0


def test_onset_tolerance_and_one_to_one_matching() -> None:
    reference = [Event(1.0, "kick"), Event(1.02, "kick")]
    prediction = [Event(1.01, "kick"), Event(1.011, "kick"), Event(1.2, "kick")]
    metrics = evaluate(reference, prediction, tolerance=0.02)["overall"]
    assert metrics["true_positives"] == 2
    assert metrics["false_positives"] == 1
    assert metrics["false_negatives"] == 0


def test_wrong_instrument_is_not_counted_as_hit() -> None:
    report = evaluate([Event(0.5, "snare")], [Event(0.5, "kick")])
    assert report["overall"]["true_positives"] == 0
    assert report["overall"]["false_positives"] == 1
    assert report["overall"]["false_negatives"] == 1


def test_instrument_aliases_are_normalized() -> None:
    assert normalize_instrument("Bass Drum") == "kick"
    assert normalize_instrument("closed-hihat") == "closed_hat"


def test_drumscript_pitch_map_matches_upstream_notation_constants() -> None:
    assert DRUMSCRIPT_DRUM_MAP == {
        36: "kick",
        38: "snare",
        41: "low_tom",
        45: "mid_tom",
        48: "high_tom",
        42: "closed_hat",
        46: "open_hat",
        49: "crash",
        51: "ride",
    }
