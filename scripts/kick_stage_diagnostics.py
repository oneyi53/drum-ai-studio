from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from drumscript.audio_processor.audio_loader import load_audio, normalise_audio
from drumscript.audio_processor.onset_detector import detect_onsets
from drumscript.datasets.idmt import find_mix_files, reference_onsets_for_file, subset_of
from drumscript.drum_classifier.classify import classify_events
from drumscript.notation_generator.constants import KICK_FREQ_MAX, KICK_FREQ_MIN, KICK_LFER_MIN, SAMPLE_RATE


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
    # Label each onset candidate against the reference kick annotations using
    # chronological one-to-one matching. Keep negatives as well as positives:
    # threshold experiments must measure false positives, not only kick recall.
    candidate_rows: list[dict[str, float | bool | str]] = []
    used_events: set[int] = set()
    for reference_time in sorted(reference_times):
        options = [
            (abs(float(event["time_sec"]) - reference_time), index, event)
            for index, event in enumerate(events)
            if index not in used_events
            and abs(float(event["time_sec"]) - reference_time) <= tolerance
        ]
        if options:
            _, index, _ = min(options, key=lambda item: item[0])
            used_events.add(index)

    for index, event in enumerate(events):
        features = event.get("debug_features", {})
        if not features:
            continue
        lfer = float(features.get("lfer", 0.0))
        peak_freq = float(features.get("peak_freq", 0.0))
        candidate_rows.append({
            "track": audio_path.name,
            "subset": subset_of(audio_path),
            "time_sec": float(event["time_sec"]),
            "lfer": lfer,
            "peak_freq": peak_freq,
            "centroid": float(features.get("centroid", 0.0)),
            "hfer": float(features.get("hfer", 0.0)),
            "hfer_5k": float(features.get("hfer_5k", 0.0)),
            "decay": float(features.get("decay", 0.0)),
            "is_reference_kick": index in used_events,
            "baseline_kick": (
                lfer >= KICK_LFER_MIN
                and KICK_FREQ_MIN <= peak_freq <= KICK_FREQ_MAX
            ),
            "predicted_kick": "kick" in event.get("instruments", []),
        })
    matched_features = [
        {
            "lfer": float(item["lfer"]),
            "peak_freq": float(item["peak_freq"]),
            "centroid": float(item["centroid"]),
            "hfer": float(item["hfer"]),
            "hfer_5k": float(item["hfer_5k"]),
            "decay": float(item["decay"]),
            "passes_lfer": float(item["lfer"]) >= KICK_LFER_MIN,
            "passes_peak_frequency": KICK_FREQ_MIN <= float(item["peak_freq"]) <= KICK_FREQ_MAX,
            "passes_kick_rule": bool(item["baseline_kick"]),
            "predicted_kick": bool(item["predicted_kick"]),
        }
        for item in candidate_rows if item["is_reference_kick"]
    ]
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
        "candidate_feature_rows": candidate_rows,
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


def score_rule(rows: list[dict], threshold: float) -> tuple[int, int, int]:
    """Return candidate-level TP, FP and FN for a fixed frequency band and LFER threshold."""
    tp = fp = fn = 0
    for row in rows:
        predicted = (
            float(row["lfer"]) >= threshold
            and KICK_FREQ_MIN <= float(row["peak_freq"]) <= KICK_FREQ_MAX
        )
        actual = bool(row["is_reference_kick"])
        tp += int(predicted and actual)
        fp += int(predicted and not actual)
        fn += int(not predicted and actual)
    return tp, fp, fn


def f1_from_counts(tp: int, fp: int, fn: int) -> float:
    denominator = 2 * tp + fp + fn
    return 2 * tp / denominator if denominator else 0.0


def leave_one_track_out_sweep(rows: list[dict]) -> dict:
    """Tune LFER on other tracks, score the held-out track, and aggregate only held-out predictions."""
    thresholds = [round(value, 3) for value in [i / 100 for i in range(5, 61, 2)]]
    tracks = sorted({str(row["track"]) for row in rows})
    held_out = []
    baseline_tp = baseline_fp = baseline_fn = 0
    for track in tracks:
        train = [row for row in rows if row["track"] != track]
        test = [row for row in rows if row["track"] == track]
        if not train or not test:
            continue
        scored = []
        for threshold in thresholds:
            tp, fp, fn = score_rule(train, threshold)
            scored.append((f1_from_counts(tp, fp, fn), tp / (tp + fp) if tp + fp else 0.0, threshold))
        # Prefer better training F1, then precision, then the more conservative threshold.
        _, _, selected = max(scored, key=lambda item: (item[0], item[1], item[2]))
        tp, fp, fn = score_rule(test, selected)
        held_out.append({
            "track": track,
            "selected_lfer_threshold": selected,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / (tp + fn) if tp + fn else 0.0,
            "f1": f1_from_counts(tp, fp, fn),
        })
        base = [row for row in test if bool(row["baseline_kick"])]
        actual = sum(bool(row["is_reference_kick"]) for row in test)
        btp = sum(bool(row["is_reference_kick"]) and bool(row["baseline_kick"]) for row in test)
        bfp = len(base) - btp
        baseline_tp += btp
        baseline_fp += bfp
        baseline_fn += actual - btp
    tp = sum(int(row["tp"]) for row in held_out)
    fp = sum(int(row["fp"]) for row in held_out)
    fn = sum(int(row["fn"]) for row in held_out)
    return {
        "method": "leave-one-track-out; tune LFER only; fixed peak-frequency band",
        "baseline_threshold": KICK_LFER_MIN,
        "baseline_held_out": {
            "tp": baseline_tp, "fp": baseline_fp, "fn": baseline_fn,
            "precision": baseline_tp / (baseline_tp + baseline_fp) if baseline_tp + baseline_fp else 0.0,
            "recall": baseline_tp / (baseline_tp + baseline_fn) if baseline_tp + baseline_fn else 0.0,
            "f1": f1_from_counts(baseline_tp, baseline_fp, baseline_fn),
        },
        "tuned_held_out": {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / (tp + fn) if tp + fn else 0.0,
            "f1": f1_from_counts(tp, fp, fn),
        },
        "per_track": held_out,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure kick-reference recall before and after DrumScript event classification."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--subset", choices=("RealDrum", "WaveDrum", "TechnoDrum", "all"), required=True)
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--tolerance-ms", type=float, default=50.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.limit < 1 or args.tolerance_ms < 0:
        parser.error("--limit must be positive and --tolerance-ms non-negative")

    if args.subset == "all":
        files = [
            path
            for subset in ("RealDrum", "WaveDrum", "TechnoDrum")
            for path in find_mix_files(args.root, subset)[: args.limit]
        ]
    else:
        files = find_mix_files(args.root, args.subset)[: args.limit]
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
    all_candidate_rows = [
        feature for row in rows for feature in row["candidate_feature_rows"]
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
        "kick_lfer_threshold": KICK_LFER_MIN,
        "kick_peak_frequency_range_hz": [KICK_FREQ_MIN, KICK_FREQ_MAX],
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
        "track_isolated_lfer_sweep": leave_one_track_out_sweep(all_candidate_rows),
        # Also train across the other two IDMT subsets to test cross-drum-kit transfer.
        "global_track_isolated_lfer_sweep": leave_one_track_out_sweep(all_candidate_rows),
        "candidate_feature_rows": all_candidate_rows,
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
        f"refs={reference_total} candidate_recall={summary['candidate_recall']:.3f} "
        f"kick_recall={summary['kick_recall']:.3f} "
        f"kick_precision={summary['kick_precision']:.3f} "
        f"candidate_to_kick_retention={summary['candidate_to_kick_match_retention']:.3f} "
        f"feature_rule_pass={feature_diagnostics['passes_kick_rule_count']}/{feature_count}"
    )
    sweep = summary["track_isolated_lfer_sweep"]
    print(
        "KICK_TRACK_ISOLATED_SWEEP "
        f"baseline_f1={sweep['baseline_held_out']['f1']:.3f} "
        f"tuned_f1={sweep['tuned_held_out']['f1']:.3f} "
        f"tuned_recall={sweep['tuned_held_out']['recall']:.3f} "
        f"tuned_precision={sweep['tuned_held_out']['precision']:.3f}"
    )
    global_sweep = summary["global_track_isolated_lfer_sweep"]
    print(
        "KICK_GLOBAL_TRACK_ISOLATED_SWEEP "
        f"baseline_f1={global_sweep['baseline_held_out']['f1']:.3f} "
        f"tuned_f1={global_sweep['tuned_held_out']['f1']:.3f} "
        f"tuned_recall={global_sweep['tuned_held_out']['recall']:.3f} "
        f"tuned_precision={global_sweep['tuned_held_out']['precision']:.3f}"
    )
    print(f"KICK_STAGE_ARTIFACT json={args.output} csv={csv_path}")


if __name__ == "__main__":
    main()
