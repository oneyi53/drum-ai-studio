from __future__ import annotations

import argparse
import json
from pathlib import Path

from kick_stage_diagnostics import leave_one_track_out_sweep


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate per-subset kick features and run cross-subset held-out validation."
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows: list[dict] = []
    subset_summaries = {}
    for subset in ("RealDrum", "WaveDrum", "TechnoDrum"):
        source = args.input_dir / f"{subset.lower()}.json"
        summary = json.loads(source.read_text())
        subset_summaries[subset] = {
            "tracks": summary["tracks_evaluated"],
            "kick_reference_events": summary["kick_reference_events"],
        }
        rows.extend(summary["candidate_feature_rows"])

    result = {
        "method": "leave-one-track-out; train on all other tracks across all IDMT subsets",
        "subsets": subset_summaries,
        "tracks_evaluated": len({row["track"] for row in rows}),
        "candidate_feature_rows": len(rows),
        "global_track_isolated_lfer_sweep": leave_one_track_out_sweep(rows),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    sweep = result["global_track_isolated_lfer_sweep"]
    baseline = sweep["baseline_held_out"]
    tuned = sweep["tuned_held_out"]
    print(
        "KICK_GLOBAL_TRACK_ISOLATED_SWEEP "
        f"tracks={result['tracks_evaluated']} candidates={len(rows)} "
        f"baseline_f1={baseline['f1']:.3f} tuned_f1={tuned['f1']:.3f} "
        f"tuned_recall={tuned['recall']:.3f} tuned_precision={tuned['precision']:.3f}"
    )


if __name__ == "__main__":
    main()
