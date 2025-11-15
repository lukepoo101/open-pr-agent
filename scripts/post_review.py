"""Convert agent output JSON into a GitHub review payload."""

from __future__ import annotations

import json
import sys
import os
from pathlib import Path


def build_review_payload(agent_output: dict) -> dict:
    decision = agent_output.get("decision", "COMMENT")
    summary = agent_output.get("summary", "")
    comments = agent_output.get("comments", []) or []

    inline_comments = []
    general_notes: list[str] = []

    for comment in comments:
        path = comment.get("path")
        line = comment.get("line")
        body = comment.get("comment", "").strip()
        if not path or not body:
            continue
        if isinstance(line, int):
            inline_comments.append(
                {
                    "path": path,
                    "line": line,
                    "side": "RIGHT",
                    "body": body,
                }
            )
        else:
            general_notes.append(f"- {path}: {body}")

    body_lines = [summary.strip() or "Automated review result."]
    if general_notes:
        body_lines.append("")
        body_lines.append("Additional notes:")
        body_lines.extend(general_notes)

    payload = {
        "event": decision,
        "body": "\n".join(body_lines).strip(),
    }

    if inline_comments:
        payload["comments"] = inline_comments

    allow_approvals = os.getenv("OPEN_PR_AGENT_ALLOW_APPROVALS", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if payload["event"] == "APPROVE" and not allow_approvals:
        payload["event"] = "COMMENT"
        payload["body"] = (
            payload["body"]
            + "\n\n"
            + "_Auto-review would approve, but this token cannot submit approvals._"
        ).strip()

    return payload


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: post_review.py <agent_output.json> <payload.json>")

    agent_output_path = Path(sys.argv[1])
    payload_path = Path(sys.argv[2])

    try:
        agent_output_raw = agent_output_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"Agent output file not found: {agent_output_path}") from exc

    if not agent_output_raw.strip():
        raise SystemExit(
            f"Agent output file is empty: {agent_output_path}. Check earlier workflow steps."
        )

    try:
        agent_output = json.loads(agent_output_raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Agent output file {agent_output_path} does not contain valid JSON: {exc}"
        ) from exc

    payload = build_review_payload(agent_output)

    payload_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
