"""Emit composite-action outputs for the Open PR Agent review."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _write_output_line(handle, key: str, value: str) -> None:
    handle.write(f"{key}={value}\n")


def _write_multiline_output(handle, key: str, value: str) -> None:
    marker = "EOF_REVIEW_BODY"
    while marker in value:
        marker += "_X"
    handle.write(f"{key}<<{marker}\n{value}\n{marker}\n")


def emit_outputs(agent_output_path: Path, payload_path: Path, outputs_path: Path) -> None:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    body = payload.get("body", "") or ""
    event = payload.get("event", "") or ""

    with outputs_path.open("a", encoding="utf-8") as handle:
        _write_output_line(handle, "agent-output-path", str(agent_output_path))
        _write_output_line(handle, "payload-path", str(payload_path))
        _write_output_line(handle, "review-event", event)
        _write_multiline_output(handle, "review-body", body)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Emit GitHub Action outputs describing the generated review payload."
    )
    parser.add_argument("--agent-output-path", required=True, type=Path)
    parser.add_argument("--payload-path", required=True, type=Path)
    parser.add_argument(
        "--outputs-file",
        type=Path,
        help="File to append step outputs to (defaults to $GITHUB_OUTPUT).",
    )

    args = parser.parse_args()

    outputs_path = args.outputs_file or os.getenv("GITHUB_OUTPUT")
    if not outputs_path:
        raise SystemExit(
            "No outputs file provided; pass --outputs-file or set the GITHUB_OUTPUT env var."
        )

    emit_outputs(args.agent_output_path, args.payload_path, Path(outputs_path))


if __name__ == "__main__":
    main()
