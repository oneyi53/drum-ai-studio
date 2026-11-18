"""Export the pinned upstream checkpoint using its embedded training metadata.

This avoids using a stale ONNX export whose input dimensions disagree with the
training source. The checkpoint is evaluated only; do not ship it in production.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import torch
import onnx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.upstream_root))
    from utils.model import DrumCNN

    checkpoint_bytes = args.checkpoint.read_bytes()
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    required = ("context", "n_mels", "n_classes", "sr", "hop_length", "n_fft", "model_state_dict")
    missing = [key for key in required if key not in checkpoint]
    if missing:
        raise SystemExit(f"checkpoint is missing training metadata: {missing}")

    spec = {
        "context": int(checkpoint["context"]),
        "n_mels": int(checkpoint["n_mels"]),
        "n_classes": int(checkpoint["n_classes"]),
        "sample_rate": int(checkpoint["sr"]),
        "hop_length": int(checkpoint["hop_length"]),
        "n_fft": int(checkpoint["n_fft"]),
        "source_commit": args.source_commit,
        "checkpoint_sha256": hashlib.sha256(checkpoint_bytes).hexdigest(),
        "model_license": "AGPL-3.0; evaluation-only",
    }
    if (spec["sample_rate"], spec["hop_length"], spec["n_fft"]) != (22050, 256, 1024):
        raise SystemExit(f"unexpected checkpoint audio feature config: {spec}")
    if spec["n_classes"] != 3 or spec["context"] != 3:
        raise SystemExit(f"unexpected checkpoint architecture config: {spec}")

    model = DrumCNN(
        n_mels=spec["n_mels"],
        context=spec["context"],
        n_classes=spec["n_classes"],
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.zeros(1, 3, 2 * spec["context"] + 1, spec["n_mels"])
    torch.onnx.export(
        model,
        dummy,
        str(args.output),
        export_params=True,
        opset_version=17,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["logits"],
        dynamic_axes={"input": {0: "batch_size"}, "logits": {0: "batch_size"}},
        dynamo=False,
    )
    exported = onnx.load(str(args.output))
    onnx.checker.check_model(exported)

    actual_shape = [dim.dim_value if dim.dim_value else None
                    for dim in exported.graph.input[0].type.tensor_type.shape.dim]
    expected_shape = [None, 3, 2 * spec["context"] + 1, spec["n_mels"]]
    if actual_shape != expected_shape:
        raise SystemExit(f"exported ONNX shape {actual_shape} != checkpoint shape {expected_shape}")

    args.output.with_suffix(".json").write_text(
        json.dumps(spec, indent=2) + "\\n", encoding="utf-8"
    )
    print("KICK_CHECKPOINT_CONFIG " + json.dumps(spec, sort_keys=True))
    print(f"KICK_ONNX_INPUT_SHAPE {actual_shape}")


if __name__ == "__main__":
    main()
