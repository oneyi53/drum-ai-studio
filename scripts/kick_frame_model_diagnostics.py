"""Compare a STAR-trained frame-level kick model with DrumScript on IDMT.

The external reference model is used for evaluation only. Its upstream repository
is AGPL-3.0; do not bundle its ONNX weights or enable it in production without a
separate licence review. This script evaluates raw full mixes on both arms so the
comparison does not mix separator/EQ changes with classifier changes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import onnxruntime as ort

from drumscript.audio_processor.audio_loader import load_audio, normalise_audio
from drumscript.audio_processor.onset_detector import detect_onsets
from drumscript.datasets.idmt import find_mix_files, reference_onsets_for_file, subset_of
from drumscript.drum_classifier import classify as classify_module
from drumscript.drum_classifier.classify import classify_events
from drumscript.notation_generator.constants import SAMPLE_RATE

MODEL_SOURCE = "https://github.com/FrancescoZumo/frame_level_drum_classifier"
MODEL_SOURCE_COMMIT = "32b1c9e43fbaede862116ef6241fa9defba39b90"
MODEL_LICENSE = "AGPL-3.0; evaluation-only, not a production dependency"
MODEL_SR = 22050
HOP_LENGTH = 256
N_FFT = 1024
N_MELS = 96
CONTEXT = 3
MODEL_THRESHOLD = 0.5


def match_count(reference: list[float], estimates: list[float], tolerance: float) -> int:
    """Maximum-cardinality chronological one-to-one matching within tolerance."""
    refs = sorted(float(value) for value in reference)
    preds = sorted(float(value) for value in estimates)
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


def unmatched_prediction_times(reference: list[float], estimates: list[float], tolerance: float) -> list[float]:
    """Return prediction timestamps not consumed by one-to-one chronological matching."""
    refs = sorted(float(value) for value in reference)
    preds = sorted(float(value) for value in estimates)
    i = 0
    false_positives: list[float] = []
    for prediction in preds:
        while i < len(refs) and refs[i] < prediction - tolerance:
            i += 1
        if i < len(refs) and abs(refs[i] - prediction) <= tolerance:
            i += 1
        else:
            false_positives.append(prediction)
    return false_positives


def score(reference: list[float], estimates: list[float], tolerance: float) -> dict[str, int | float]:
    tp = match_count(reference, estimates, tolerance)
    fp = len(estimates) - tp
    fn = len(reference) - tp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "reference_kicks": len(reference),
        "predicted_kicks": len(estimates),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def probabilities_to_onsets(probabilities: np.ndarray, threshold: float, hop_length: int = HOP_LENGTH, sample_rate: int = MODEL_SR) -> list[float]:
    """Convert the model's frame-wise kick probability to rising-edge onsets."""
    values = np.asarray(probabilities, dtype=np.float64).reshape(-1)
    active = values > threshold
    rising = np.zeros_like(active, dtype=bool)
    rising[1:] = active[1:] & ~active[:-1]
    return (np.flatnonzero(rising) * hop_length / sample_rate).astype(float).tolist()


def _model_features(audio_path: Path, model_spec: dict[str, Any]) -> np.ndarray:
    sample_rate = int(model_spec['sample_rate'])
    waveform, _ = librosa.load(str(audio_path), sr=sample_rate, mono=True)
    mel = librosa.feature.melspectrogram(
        y=waveform, sr=sample_rate, n_fft=int(model_spec['n_fft']),
        hop_length=int(model_spec['hop_length']), n_mels=int(model_spec['n_mels'])
    )
    log_mel = librosa.power_to_db(mel, ref=np.max)
    delta = librosa.feature.delta(log_mel)
    delta2 = librosa.feature.delta(log_mel, order=2)
    return np.stack((log_mel, delta, delta2), axis=0).astype(np.float32)


def infer_frame_model(session: ort.InferenceSession, audio_path: Path, model_spec: dict[str, Any]) -> list[float]:
    features = _model_features(audio_path, model_spec)
    frame_count = features.shape[-1]
    context = int(model_spec['context'])
    pad = np.zeros((3, int(model_spec['n_mels']), context), dtype=np.float32)
    padded = np.concatenate((pad, features, pad), axis=2)
    windows = np.lib.stride_tricks.sliding_window_view(
        padded, 2 * context + 1, axis=2
    ).transpose(2, 0, 3, 1)
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    probability_chunks: list[np.ndarray] = []
    for start in range(0, frame_count, 4096):
        logits = session.run(
            [output_name], {input_name: np.ascontiguousarray(windows[start : start + 4096])}
        )[0]
        logits = np.asarray(logits, dtype=np.float64)
        probability_chunks.append(1.0 / (1.0 + np.exp(-np.clip(logits, -80.0, 80.0))))
    probabilities = np.concatenate(probability_chunks, axis=0)
    if probabilities.ndim != 2 or probabilities.shape[1] < 1:
        raise RuntimeError(f"unexpected model output shape: {probabilities.shape}")
    return probabilities_to_onsets(probabilities[:, 0], MODEL_THRESHOLD, hop_length=int(model_spec['hop_length']), sample_rate=int(model_spec['sample_rate']))


def _drumscript_kicks(audio_path: Path, lfer_min: float) -> list[float]:
    audio, sample_rate = load_audio(str(audio_path), sr=SAMPLE_RATE)
    audio = normalise_audio(audio)
    onsets = detect_onsets(audio, sample_rate)
    original = classify_module.KICK_LFER_MIN
    try:
        classify_module.KICK_LFER_MIN = lfer_min
        events = classify_events(audio, sample_rate, onsets)
    finally:
        classify_module.KICK_LFER_MIN = original
    return sorted(
        float(event["time_sec"])
        for event in events
        if "kick" in event.get("instruments", [])
    )


def _aggregate(rows: list[dict[str, Any]], prefix: str) -> dict[str, int | float]:
    reference_total = sum(int(row[f"{prefix}_reference_kicks"]) for row in rows)
    prediction_total = sum(int(row[f"{prefix}_predicted_kicks"]) for row in rows)
    tp = sum(int(row[f"{prefix}_tp"]) for row in rows)
    fp = sum(int(row[f"{prefix}_fp"]) for row in rows)
    fn = sum(int(row[f"{prefix}_fn"]) for row in rows)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "reference_kicks": reference_total,
        "predicted_kicks": prediction_total,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def evaluate_subset(
    root: Path,
    subset_name: str,
    model_path: Path,
    output_path: Path,
    limit: int | None,
    offset: int,
    tolerance_ms: float,
) -> dict[str, Any]:
    files = find_mix_files(root, subset_name)
    files = files[offset : offset + limit if limit is not None else None]
    if not files:
        raise ValueError(f"no IDMT mix files found for subset {subset_name!r}")
    model_spec_path = model_path.with_suffix(".json")
    if not model_spec_path.is_file():
        raise FileNotFoundError(f"checkpoint-derived metadata missing: {model_spec_path}")
    model_spec = json.loads(model_spec_path.read_text(encoding="utf-8"))
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_shape = session.get_inputs()[0].shape
    expected_shape = [None, 3, 2 * int(model_spec["context"]) + 1, int(model_spec["n_mels"])]
    actual_shape = [None if isinstance(value, str) else value for value in input_shape]
    if actual_shape != expected_shape:
        raise RuntimeError(f"ONNX input shape {actual_shape} does not match checkpoint metadata {expected_shape}")
    rows: list[dict[str, Any]] = []
    false_positive_rows: list[dict[str, Any]] = []
    tolerance = tolerance_ms / 1000.0

    for audio_path in files:
        references = reference_onsets_for_file(audio_path).get("KD", [])
        reference_times = [float(value) for value in references]
        model_times = infer_frame_model(session, audio_path, model_spec)
        rule010_times = _drumscript_kicks(audio_path, 0.10)
        rule032_times = _drumscript_kicks(audio_path, 0.32)
        row: dict[str, Any] = {
            "track": audio_path.name,
            "subset": subset_of(audio_path),
            "tolerance_ms": tolerance_ms,
        }
        all_references = reference_onsets_for_file(audio_path)
        other_refs = {
            "SD": [float(value) for value in all_references.get("SD", [])],
            "HH": [float(value) for value in all_references.get("HH", [])],
        }
        for prefix, estimates in (
            ("frame_model", model_times),
            ("drumscript_lfer_010", rule010_times),
            ("drumscript_lfer_032", rule032_times),
        ):
            metrics = score(reference_times, estimates, tolerance)
            for key, value in metrics.items():
                row[f"{prefix}_{key}"] = value
            fp_times = unmatched_prediction_times(reference_times, estimates, tolerance)
            row[f"{prefix}_fp_times_sec"] = json.dumps([round(t, 4) for t in fp_times])
            for fp_time in fp_times:
                nearest = {code: min(values, key=lambda t: abs(t - fp_time)) if values else None for code, values in other_refs.items()}
                distances = {code: abs(value - fp_time) for code, value in nearest.items() if value is not None}
                closest = min(distances, key=distances.get) if distances else None
                nearest_time = nearest.get(closest) if closest else None
                coincident = nearest_time is not None and abs(nearest_time - fp_time) <= 0.10
                false_positive_rows.append({
                    "track": audio_path.name, "subset": subset_of(audio_path), "arm": prefix,
                    "fp_time_sec": round(fp_time, 4),
                    "nearest_other_drum": closest if coincident else "",
                    "nearest_other_drum_time_sec": round(nearest_time, 4) if nearest_time is not None else "",
                    "nearest_other_drum_delta_ms": round((nearest_time - fp_time) * 1000, 1) if nearest_time is not None else "",
                    "interpretation": "coincident_non_kick_drum" if coincident else "unmatched_by_IDMT_drum_annotations",
                })
        rows.append(row)

    prefixes = ("frame_model", "drumscript_lfer_010", "drumscript_lfer_032")
    summary = {
        "schema_version": "1.0",
        "subset": subset_name,
        "tracks_evaluated": len(rows),
        "track_offset": offset,
        "tolerance_ms": tolerance_ms,
        "model_source": MODEL_SOURCE,
        "model_source_commit": MODEL_SOURCE_COMMIT,
        "model_license": MODEL_LICENSE,
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "checkpoint_training_config": model_spec,
        "model_input_shape": input_shape,
        "false_positive_interpretation": "IDMT annotates kick/snare/hi-hat, not bass guitar or synthesizer. False positives coincident with annotated snare/hi-hat are tagged; remaining events require stem/audio review and must not be labeled bass/synth automatically.",
        "drumscript_source_sha": os.environ.get("DRUMSCRIPT_SHA", "not-recorded"),
        "comparison_scope": (
            "All three classifiers receive the same original full mix. "
            "This is not the production Demucs+EQ app path."
        ),
        "aggregates": {prefix: _aggregate(rows, prefix) for prefix in prefixes},
        "tracks": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    csv_path = output_path.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fp_csv_path = output_path.with_name(output_path.stem + "_false_positives.csv")
    fp_fields = ["track", "subset", "arm", "fp_time_sec", "nearest_other_drum", "nearest_other_drum_time_sec", "nearest_other_drum_delta_ms", "interpretation"]
    with fp_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fp_fields)
        writer.writeheader()
        writer.writerows(false_positive_rows)
    for prefix in prefixes:
        metrics = summary["aggregates"][prefix]
        print(
            f"KICK_MODEL_EVAL subset={subset_name} arm={prefix} tracks={len(rows)} "
            f"refs={metrics['reference_kicks']} pred={metrics['predicted_kicks']} "
            f"TP={metrics['tp']} FP={metrics['fp']} FN={metrics['fn']} "
            f"P={metrics['precision']:.4f} R={metrics['recall']:.4f} F1={metrics['f1']:.4f}"
        )
    print(f"KICK_MODEL_ARTIFACT json={output_path} csv={csv_path} false_positives={fp_csv_path}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare a STAR-trained frame-level kick model with DrumScript on IDMT."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--subset", choices=("RealDrum", "WaveDrum", "TechnoDrum"), required=True
    )
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--tolerance-ms", type=float, default=50.0)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.offset < 0 or args.tolerance_ms < 0:
        parser.error("--offset and --tolerance-ms must be non-negative")
    if not args.model.is_file() or args.model.stat().st_size < 100_000:
        parser.error("--model must be a downloaded ONNX model, not a Git LFS pointer")
    evaluate_subset(
        args.root,
        args.subset,
        args.model,
        args.output,
        args.limit,
        args.offset,
        args.tolerance_ms,
    )


if __name__ == "__main__":
    main()
