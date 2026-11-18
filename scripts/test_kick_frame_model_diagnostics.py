from __future__ import annotations

import numpy as np
import pytest

from kick_frame_model_diagnostics import match_count, probabilities_to_onsets, score


def test_match_count_uses_chronological_maximum_cardinality_assignment():
    # Greedy minimum-error pair selection can incorrectly return one match here.
    assert match_count([0.000, 0.050], [0.020, -0.040], 0.050) == 2


def test_match_count_never_reuses_a_prediction_or_reference():
    assert match_count([0.0], [-0.01, 0.01], 0.05) == 1
    assert match_count([0.0, 0.0], [0.0], 0.05) == 1


def test_frame_probabilities_emit_rising_edges_including_frame_zero():
    probabilities = np.array([0.7, 0.8, 0.2, 0.6, 0.9], dtype=np.float32)
    expected = [0.0, 3 * 256 / 22050]
    assert probabilities_to_onsets(probabilities, 0.5) == pytest.approx(expected)


def test_frame_probabilities_respect_threshold():
    probabilities = np.array([0.49, 0.51, 0.5, 0.49, 0.5], dtype=np.float32)
    expected = [256 / 22050, 4 * 256 / 22050]
    assert probabilities_to_onsets(probabilities, 0.5) == pytest.approx(expected)


def test_score_reports_precision_recall_f1_and_all_error_counts():
    result = score([0.0, 0.5], [-0.04, 0.02, 0.5], 0.05)
    assert result["tp"] == 2
    assert result["fp"] == 1
    assert result["fn"] == 0
    assert result["precision"] == pytest.approx(2 / 3)
    assert result["recall"] == pytest.approx(1.0)
    assert result["f1"] == pytest.approx(0.8)
