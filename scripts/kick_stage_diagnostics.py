from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from drumscript.audio_processor.audio_loader import load_audio, normalise_audio
from drumscript.audio_processor.onset_detector import detect_onsets
from drumscript.datasets.idmt import (
    find_mix_files,
    reference_onsets_for_file,
    subset_of,
)
from drumscript.drum_classifier import classify as classify_module
from drumscript.drum_classifier.classify import classify_events
from drumscript.notation_generator.constants import SAMPLE_RATE


def apply_kick_thresholds(lfer_min: float, peak_freq_min: float, peak_freq_max: float) -> None:
    """Override the upstream kick gate for this diagnostic process.

    ``classify_events`` reads the thresholds from its own module globals
    (bound at import time from the constants module), so the constants
    module alone must not be patched. Both modules are updated so the
    reported threshold always matches the behaviour under test.
    """
    if not 0.0 <= lfer_min <= 1.0:
        raise ValueError(f"--lfer-min must be within [0, 1], got {lfer_min}")
    if not 0.0 < peak_freq_min < peak_freq_max:
        raise ValueError(
            "--peak-freq range must satisfy 0 < min < max, got "
            f"({peak_freq_min}, {peak_freq_max})"
        )
    classify_module.KICK_LFER_MIN = lfer_min
    classify_module.KICK_FREQ_MIN = peak_freq_min
    classify_module.KICK_FREQ_MAX = peak_freq_max


def match_count(reference: list[float], estimates: list[float], tolerance: float) -> int:
    """Count one-to-one chronological matches within the timing tolerance."""
    refs = sorted(reference)
    preds = sorted(estimates)
    i = j = matched = 0
    while i < len(refs) and j < len(preds):
        delta = preds[j] - refs[i]
        if abs(delta) <= tolerance:
            matched += 1
            i += 1
            j += 1
        elif delta < -tolerance:
            j += 1
        else:
            i += 1
    return matched


def evaluate_file(audio_path: Path, tolerance: float) -> dict[str, int | float | str]:
    audio, sample_rate = load_audio(str(audio_path), sr=SAMPLE_RATE)
    audio = normalise_audio(audio)
    onsets = detect_onsets(audio, sample_rate)
    events = classify_events(audio, sample_rate, onsets)

    references_by_code = reference_onsets_for_file(audio_path)
    kick_references = references_by_code.get("KD", [])
    reference_times = [float(value) for value in kick_references]
    candidate_times = [float(value) for value in onsets]
    kick_times = sorted(
        float(event["time_sec"])
        for event in events
        if "kick" in event.get("instruments", [])
    )

    candidate_tp = match_count(reference_times, candidate_times, tolerance)
    kick_tp = match_count(reference_times, kick_times, tolerance)

    # Inspect classifier features for reference kicks that already have an onset candidate.
    matched_features: list[dict[str, float | bool]] = []
    used_candidates: set[int] = set()
    for reference_time in sorted(reference_times):
        options = [
            (abs(float(event["time_sec"]) - reference_time), index, event)
            for index, event in enumerate(events)
            if index not in used_candidates
            and abs(float(event["time_sec"]) - reference_time) <= tolerance
        ]
        if not options:
            continue
        _, index, event = min(options, key=lambda item: item[0])
        used_candidates.add(index)
        features = event.get("debug_features", {})
        if not features:
            continue
        lfer = float(features.get("lfer", 0.0))
        peak_freq = float(features.get("peak_freq", 0.0))
        matched_features.append({
            "lfer": lfer,
            "peak_freq": peak_freq,
            "centroid": float(features.get("centroid", 0.0)),
            "hfer": float(features.get("hfer", 0.0)),
            "hfer_5k": float(features.get("hfer_5k", 0.0)),
            "decay": float(features.get("decay", 0.0)),
            "passes_lfer": lfer >= classify_module.KICK_LFER_MIN,
            "passes_peak_frequency": classify_module.KICK_FREQ_MIN <= peak_freq <= classify_module.KICK_FREQ_MAX,
            "passes_kick_rule": lfer >= classify_module.KICK_LFER_MIN and classify_module.KICK_FREQ_MIN <= peak_freq <= classify_module.KICK_FREQ_MAX,
            "predicted_kick": "kick" in event.get("instruments", []),
        })
    return {
        "track": audio_path.name,
        "subset": subset_of(audio_path),
        "kick_reference": len(reference_times),
        "onset_candidates": len(candidate_times),
        "candidate_matches": candidate_tp,
        "kick_predictions": len(kick_times),
        "kick_matches": kick_tp,
        "candidate_recall": candidate_tp / len(reference_times) if reference_times else 0.0,
        "kick_recall": kick_tp / len(reference_times) if reference_times else 0.0,
        "kick_precision": kick_tp / len(kick_times) if kick_times else 0.0,
        "matched_candidate_kick_features": matched_features,
    }


def feature_distribution(items: list[dict], key: str) -> dict[str, float | int | None]:
    """Summarize reference-aligned onset features by classifier outcome."""
    values = sorted(float(item[key]) for item in items if item.get(key) is not None)
    if not values:
        return {"count": 0, "p25": None, "median": None, "p75": None}
    return {
        "count": len(values),
        "p25": values[int((len(values) - 1) * 0.25)],
        "median": values[len(values) // 2],
        "p75": values[int((len(values) - 1) * 0.75)],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure kick-reference recall before and after DrumScript event classification."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--subset", choices=("RealDrum", "WaveDrum", "TechnoDrum"), required=True)
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip this many mix files before taking --limit tracks. Use it to "
        "evaluate a candidate threshold on tracks that were not used to select "
        "it (held-out validation).",
    )
    parser.add_argument("--tolerance-ms", type=float, default=50.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--lfer-min",
        type=float,
        default=classify_module.KICK_LFER_MIN,
        help="Override the upstream kick LFER gate (default: upstream KICK_LFER_MIN). "
        "Use with the adapter's KickClassificationConfig to measure a candidate "
        "threshold before adopting it.",
    )
    parser.add_argument(
        "--peak-freq-min-hz",
        type=float,
        default=classify_module.KICK_FREQ_MIN,
        help="Override the upstream kick peak-frequency lower bound in Hz.",
    )
    parser.add_argument(
        "--peak-freq-max-hz",
        type=float,
        default=classify_module.KICK_FREQ_MAX,
        help="Override the upstream kick peak-frequency upper bound in Hz.",
    )
    args = parser.parse_args()

    if args.limit < 1 or args.tolerance_ms < 0 or args.offset < 0:
        parser.error("--limit must be positive and --tolerance-ms/--offset non-negative")
    try:
        apply_kick_thresholds(args.lfer_min, args.peak_freq_min_hz, args.peak_freq_max_hz)
    except ValueError as exc:
        parser.error(str(exc))

    files = find_mix_files(args.root, args.subset)[args.offset : args.offset + args.limit]
    if not files:
        parser.error(f"No IDMT mix files found for subset {args.subset}")

    rows = [evaluate_file(path, args.tolerance_ms / 1000.0) for path in files]
    reference_total = sum(int(row["kick_reference"]) for row in rows)
    candidate_tp_total = sum(int(row["candidate_matches"]) for row in rows)
    kick_tp_total = sum(int(row["kick_matches"]) for row in rows)
    kick_prediction_total = sum(int(row["kick_predictions"]) for row in rows)
    matched_features = [
        feature for row in rows for feature in row["matched_candidate_kick_features"]
    ]
    feature_count = len(matched_features)
    feature_diagnostics = {
        "matched_candidate_count": feature_count,
        "reference_aligned_predicted_kick": sum(bool(item["predicted_kick"]) for item in matched_features),
        "reference_aligned_missed_kick": sum(not bool(item["predicted_kick"]) for item in matched_features),
        "lfer_by_classifier_outcome": {
            "predicted_kick": feature_distribution(
                [item for item in matched_features if item["predicted_kick"]], "lfer"
            ),
            "missed_kick": feature_distribution(
                [item for item in matched_features if not item["predicted_kick"]], "lfer"
            ),
        },
        "peak_frequency_by_classifier_outcome": {
            "predicted_kick": feature_distribution(
                [item for item in matched_features if item["predicted_kick"]], "peak_freq"
            ),
            "missed_kick": feature_distribution(
                [item for item in matched_features if not item["predicted_kick"]], "peak_freq"
            ),
        },
        "passes_lfer_count": sum(bool(item["passes_lfer"]) for item in matched_features),
        "passes_peak_frequency_count": sum(bool(item["passes_peak_frequency"]) for item in matched_features),
        "passes_kick_rule_count": sum(bool(item["passes_kick_rule"]) for item in matched_features),
        "mean_lfer": (
            sum(float(item["lfer"]) for item in matched_features) / feature_count
            if feature_count else None
        ),
        "median_lfer": (
            sorted(float(item["lfer"]) for item in matched_features)[feature_count // 2]
            if feature_count else None
        ),
        "median_peak_freq_hz": (
            sorted(float(item["peak_freq"]) for item in matched_features)[feature_count // 2]
            if feature_count else None
        ),
        "kick_lfer_threshold": classify_module.KICK_LFER_MIN,
        "kick_peak_frequency_range_hz": [classify_module.KICK_FREQ_MIN, classify_module.KICK_FREQ_MAX],
    }

    summary = {
        "subset": args.subset,
        "tracks_evaluated": len(rows),
        "tolerance_ms": args.tolerance_ms,
        "kick_reference_events": reference_total,
        "onset_candidate_matches": candidate_tp_total,
        "kick_classification_matches": kick_tp_total,
        "kick_predictions": kick_prediction_total,
        "candidate_recall": candidate_tp_total / reference_total if reference_total else 0.0,
        "kick_recall": kick_tp_total / reference_total if reference_total else 0.0,
        "kick_precision": kick_tp_total / kick_prediction_total if kick_prediction_total else 0.0,
        "candidate_to_kick_match_retention": kick_tp_total / candidate_tp_total if candidate_tp_total else 0.0,
        "kick_rule_feature_diagnostics": feature_diagnostics,
        "tracks": rows,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    csv_path = args.output.with_suffix(".csv")
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"KICK_STAGE_DIAGNOSTICS subset={args.subset} tracks={len(rows)} "
        f"refs={reference_total} lfer_min={classify_module.KICK_LFER_MIN:.3f} "
        f"peak_freq_hz=[{classify_module.KICK_FREQ_MIN:.0f}, {classify_module.KICK_FREQ_MAX:.0f}] "
        f"candidate_recall={summary['candidate_recall']:.3f} "
        f"kick_recall={summary['kick_recall']:.3f} "
        f"kick_precision={summary['kick_precision']:.3f} "
        f"candidate_to_kick_retention={summary['candidate_to_kick_match_retention']:.3f} "
        f"feature_rule_pass={feature_diagnostics['passes_kick_rule_count']}/{feature_count}"
    )
    print(f"KICK_STAGE_ARTIFACT json={args.output} csv={csv_path}")


if __name__ == "__main__":
    main()
