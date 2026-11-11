"""Convert a MIDI file into the canonical DrumPerformance JSON format."""
from __future__ import annotations

import argparse
from pathlib import Path

from .midi_adapter import midi_to_performance


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert General MIDI percussion events to canonical DrumPerformance JSON."
    )
    parser.add_argument("midi_file", type=Path, help="Input Standard MIDI File")
    parser.add_argument("--output", "-o", type=Path, help="Output JSON path (stdout if omitted)")
    parser.add_argument(
        "--all-channels",
        action="store_true",
        help="Include note-ons from channels other than MIDI channel 10",
    )
    parser.add_argument(
        "--drop-unmapped",
        action="store_true",
        help="Skip pitches without a General MIDI percussion mapping",
    )
    args = parser.parse_args()

    performance = midi_to_performance(
        args.midi_file,
        percussion_channel_only=not args.all_channels,
        include_unmapped_notes=not args.drop_unmapped,
    )
    payload = performance.model_dump_json(indent=2) + "\\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
