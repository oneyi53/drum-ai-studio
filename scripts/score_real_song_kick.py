#!/usr/bin/env python3
"""Run CNN and DrumScript on identical openly licensed full-song mixes.

OnAir isolated-kick-stem onset proposals are provisional until reviewed by a
human. Kaino tracks are full-mix stress inputs with no ground truth and are
reported as prediction counts/timestamps only, never precision/recall/F1.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import onnxruntime as ort

from kick_frame_model_diagnostics import (
    _drumscript_kicks,
    infer_frame_model,
    score,
    unmatched_prediction_times,
)


def read_proposals(path: Path) -> tuple[list[float], bool]:
    times: list[float] = []
    statuses: list[str] = []
    if not path.exists():
        return times, False
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            times.append(float(row["time_seconds"]))
            statuses.append(row.get("review_status", "needs_human_review"))
    approved = bool(statuses) and all(value == "approved" for value in statuses)
    return times, approved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-root", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tolerance-ms", type=float, default=50.0)
    args = parser.parse_args()

    onair_manifest = json.loads((args.manifest_root / "onair-manifest.json").read_text(encoding="utf-8"))
    kaino_manifest_path = args.manifest_root / "kaino" / "kaino-manifest.json"
    kaino_manifest = json.loads(kaino_manifest_path.read_text(encoding="utf-8")) if kaino_manifest_path.exists() else []
    model_spec = json.loads(args.model.with_suffix(".json").read_text(encoding="utf-8"))
    session = ort.InferenceSession(str(args.model), providers=["CPUExecutionProvider"])
    tolerance = args.tolerance_ms / 1000.0
    results: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []

    for item in onair_manifest:
        mix = item.get("mix_path")
        if not mix or not Path(mix).is_file():
            continue
        cnn = infer_frame_model(session, Path(mix), model_spec)
        rule_low = _drumscript_kicks(Path(mix), 0.10)
        rule_stock = _drumscript_kicks(Path(mix), 0.32)
        row: dict[str, Any] = {
            "dataset": "OnAir Music Dataset V4",
            "track": item["track"],
            "tier": item["tier"],
            "license": item["license"],
            "mix_sha256": item.get("mix_sha256"),
            "pipeline": "raw_full_mix_same_file_no_demucs_no_eq",
            "cnn_prediction_count": len(cnn),
            "drumscript_lfer_010_prediction_count": len(rule_low),
            "drumscript_lfer_032_prediction_count": len(rule_stock),
            "tolerance_ms": args.tolerance_ms,
        }
        if item.get("kick_stem_path") and item.get("proposal_csv"):
            reference, approved = read_proposals(Path(item["proposal_csv"]))
            row["reference_source"] = "isolated_kick_stem_auto_onset_proposals"
            row["reference_review_status"] = "approved" if approved else "needs_human_review"
            row["provisional_cnn"] = score(reference, cnn, tolerance)
            row["provisional_drumscript_lfer_010"] = score(reference, rule_low, tolerance)
            row["provisional_drumscript_lfer_032"] = score(reference, rule_stock, tolerance)
            row["metrics_status"] = "reviewed_reference" if approved else "PROVISIONAL_NOT_FOR_ACCEPTANCE"
            for arm, predictions in (
                ("cnn", cnn), ("drumscript_lfer_010", rule_low), ("drumscript_lfer_032", rule_stock)
            ):
                for stamp in unmatched_prediction_times(reference, predictions, tolerance):
                    event_rows.append({
                        "dataset": "OnAir Music Dataset V4",
                        "track": item["track"],
                        "arm": arm,
                        "time_seconds": f"{stamp:.6f}",
                        "event_status": "unmatched_to_unreviewed_kick_proposal" if not approved else "unmatched_to_approved_kick_reference",
                        "instrument_cause": "unknown_requires_audio_and_stem_review",
                    })
        else:
            row["metrics_status"] = "NO_KICK_ONLY_GROUND_TRUTH_BASS_CONFUSION_LISTENING_ONLY"
            row["reference_source"] = None
        results.append(row)
        for arm, predictions in (
            ("cnn", cnn), ("drumscript_lfer_010", rule_low), ("drumscript_lfer_032", rule_stock)
        ):
            for stamp in predictions:
                event_rows.append({
                    "dataset": "OnAir Music Dataset V4",
                    "track": item["track"],
                    "arm": arm,
                    "time_seconds": f"{stamp:.6f}",
                    "event_status": "prediction",
                    "instrument_cause": "unreviewed",
                })

    for item in kaino_manifest:
        mix = item.get("file")
        if item.get("status") != "downloaded" or not mix or not Path(mix).is_file():
            continue
        cnn = infer_frame_model(session, Path(mix), model_spec)
        rule_low = _drumscript_kicks(Path(mix), 0.10)
        rule_stock = _drumscript_kicks(Path(mix), 0.32)
        results.append({
            "dataset": "Kaino CC0 Music Library",
            "track": item["title"],
            "license": item["license"],
            "mix_sha256": item["sha256"],
            "pipeline": "raw_full_mix_same_file_no_demucs_no_eq",
            "cnn_prediction_count": len(cnn),
            "drumscript_lfer_010_prediction_count": len(rule_low),
            "drumscript_lfer_032_prediction_count": len(rule_stock),
            "metrics_status": "NO_GROUND_TRUTH_ROBUSTNESS_ONLY",
            "reference_source": None,
            "tolerance_ms": args.tolerance_ms,
        })
        for arm, predictions in (
            ("cnn", cnn), ("drumscript_lfer_010", rule_low), ("drumscript_lfer_032", rule_stock)
        ):
            for stamp in predictions:
                event_rows.append({
                    "dataset": "Kaino CC0 Music Library",
                    "track": item["title"],
                    "arm": arm,
                    "time_seconds": f"{stamp:.6f}",
                    "event_status": "prediction_no_ground_truth",
                    "instrument_cause": "unknown_requires_human_annotation",
                })

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "real-song-comparison.json").write_text(
        json.dumps({
            "protocol": {
                "pipeline": "raw full mix for every model arm; no Demucs/EQ",
                "tolerance_ms": args.tolerance_ms,
                "cnn": "pinned STAR frame CNN checkpoint",
                "drumscript_thresholds": [0.10, 0.32],
                "warning": "Only approved kick references support acceptance metrics. Unreviewed stem proposals are provisional; Kaino has no reference labels.",
            },
            "tracks": results,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    with (args.output / "real-song-events.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "dataset", "track", "arm", "time_seconds", "event_status", "instrument_cause"
        ])
        writer.writeheader()
        writer.writerows(event_rows)
    print(json.dumps({
        "tracks_scored_or_smoke_tested": len(results),
        "onair_tracks": sum(x["dataset"] == "OnAir Music Dataset V4" for x in results),
        "kaino_tracks": sum(x["dataset"] == "Kaino CC0 Music Library" for x in results),
        "human_approved_reference_tracks": sum(x.get("metrics_status") == "reviewed_reference" for x in results),
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
