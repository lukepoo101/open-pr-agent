from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from textwrap import shorten
from typing import Literal

from openhands.sdk import Conversation, LLM, get_logger
from openhands.sdk.conversation import get_agent_final_response
from openhands.tools.preset.default import get_default_agent
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

logger = get_logger(__name__)

OPENHANDS_PROMPT = """You are an expert code reviewer. Use bash commands to analyze the PR
changes and identify issues that need to be addressed.

## Pull Request Information
- **Title**: {title}
- **Description**: {body}
- **Repository**: {repo_name}
- **Base Branch**: {base_branch}
- **Head Branch**: {head_branch}

## Analysis Process
Use bash commands to understand the changes, check out diffs and examine
the code related to the PR.

## Review Output Format
Provide a concise review focused on issues that need attention. Every issue you report
must include the concrete file path and (when possible) the exact line number(s) that
need changes. Use tools like `git diff --unified=0 <file>` or `nl -ba <file>` to capture
line numbers accurately. Cite them inline as `path/to/file.py:L42` or `path/to/file.py:L10-L15`.
If you cannot determine an exact line, explain why.
If there are no issues of a particular importance level (e.g. no critical issues), it is
OK to skip that level or even not point out any issues at all.
<FORMAT>
### Issues Found

**🔴 Critical Issues**
- [List blocking issues that prevent merge]

**🟡 Important Issues**
- [List significant issues that should be addressed]

**🟢 Minor Issues**
- [List optional improvements]
</FORMAT>

## Guidelines
- Focus ONLY on issues that need to be fixed
- Be specific and actionable
- Always cite file paths and line numbers for every issue when possible
- Follow the format above strictly
- Do NOT include lengthy positive feedback

Start by analyzing the changes with bash commands, then provide your structured review.
"""

OPENHANDS_TRANSFORM_PROMPT = (
    "You convert OpenHands agent Markdown reviews into structured review data.\n"
    "- decision: APPROVE if no blocking issues remain, otherwise REQUEST_CHANGES.\n"
    "- summary: short (<120 chars) description of the overall result.\n"
    "- comments: extract concrete files/paths plus actionable guidance.\n"
    "- When the review cites lines like `path/file.py:L12` or `path/file.py:L12-L18`,\n"
    "  set `path` to the cited file and set `line` to the first line number.\n"
    "- If no line is mentioned, leave `line` unset. Do not invent line numbers.\n"
    "- Only include comments that clearly map to files mentioned in the review text.\n"
    "- Ignore compliments or meta commentary.\n"
    "Return the result as ReviewOutput."
)

class ReviewComment(BaseModel):
    """Structured inline comment for an individual file/line."""

    path: str
    line: int | None = None
    comment: str


class ReviewOutput(BaseModel):
    """Structured review summary emitted by the agent."""

    decision: Literal["APPROVE", "REQUEST_CHANGES"]
    summary: str
    comments: list[ReviewComment] = Field(default_factory=list)


class Settings(BaseSettings):
    """Load OpenAI-compatible connection details from the environment or a .env file."""

    model_config = SettingsConfigDict(env_prefix="OPENAI_", env_file=".env", extra="ignore")

    base_url: str
    model: str
    api_key: str


def _build_model(settings: Settings) -> OpenAIChatModel:
    provider = OpenAIProvider(
        base_url=settings.base_url,
        api_key=settings.api_key,
    )
    return OpenAIChatModel(
        settings.model,
        provider=provider,
        settings=ModelSettings(temperature=0.1),
    )


def _run_structured_agent(settings: Settings, system_prompt: str, user_prompt: str) -> ReviewOutput:
    model = _build_model(settings)
    agent = Agent(model=model, output_type=ReviewOutput, system_prompt=system_prompt)
    result = agent.run_sync(user_prompt)
    return result.output


def _prepare_openhands_model(model_name: str) -> str:
    model_name = model_name.strip()
    if "/" in model_name:
        return model_name
    return f"openai/{model_name}"


def _load_pr_info(event_path: Path) -> dict[str, str]:
    with event_path.open("r", encoding="utf-8") as fh:
        event = json.load(fh)

    pull = event.get("pull_request") or {}
    if not pull:
        raise RuntimeError("Provided event payload does not contain pull_request data.")

    base = pull.get("base", {}) or {}
    head = pull.get("head", {}) or {}
    repo = base.get("repo", {}) or {}

    return {
        "number": str(pull.get("number") or event.get("number") or "unknown"),
        "title": pull.get("title") or "N/A",
        "body": pull.get("body") or "No description provided",
        "repo_name": repo.get("full_name") or os.getenv("GITHUB_REPOSITORY") or "unknown/unknown",
        "base_branch": base.get("ref") or "main",
        "head_branch": head.get("ref") or "unknown",
    }


def _fallback_review_from_text(text: str) -> ReviewOutput:
    summary_source = next((line.strip() for line in text.splitlines() if line.strip()), "OpenHands review result.")
    summary = shorten(summary_source, width=200, placeholder="...")
    return ReviewOutput(
        decision="REQUEST_CHANGES",
        summary=summary,
        comments=[
            ReviewComment(
                path="OpenHands",
                line=None,
                comment=text.strip(),
            )
        ],
    )


def run_openhands_backend(settings: Settings, event_path: Path) -> ReviewOutput:
    pr_info = _load_pr_info(event_path)
    logger.info("Running OpenHands agent for PR #%s: %s", pr_info["number"], pr_info["title"])

    llm_config: dict[str, str] = {
        "model": _prepare_openhands_model(settings.model),
        "api_key": settings.api_key,
        "service_id": "pr_review_agent",
        "drop_params": True,
    }
    if settings.base_url:
        llm_config["base_url"] = settings.base_url

    llm = LLM(**llm_config)
    agent = get_default_agent(llm=llm, cli_mode=True)
    conversation = Conversation(agent=agent, workspace=os.getcwd())

    prompt = OPENHANDS_PROMPT.format(**pr_info)
    conversation.send_message(prompt)

    # OpenHands prints the full agent transcript to stdout in CLI mode.
    # Redirect stdout to stderr while the agent runs so our JSON output remains clean.
    with redirect_stdout(sys.stderr):
        conversation.run()

    review_content = get_agent_final_response(conversation.state.events)
    if not review_content:
        raise RuntimeError("OpenHands agent did not return any review content.")

    try:
        structured = _run_structured_agent(
            settings,
            system_prompt=OPENHANDS_TRANSFORM_PROMPT,
            user_prompt=review_content,
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.error("Failed to structure OpenHands output: %s", exc)
        structured = _fallback_review_from_text(review_content)

    return structured


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Open PR Agent reviewer.")
    parser.add_argument(
        "--event-path",
        default=os.getenv("GITHUB_EVENT_PATH", ""),
        help="Path to a pull_request event payload (required). Defaults to GITHUB_EVENT_PATH.",
    )
    parser.add_argument(
        "--output-path",
        default=os.getenv("AGENT_OUTPUT_PATH", "review.json"),
        help="Where to write the structured agent output (defaults to AGENT_OUTPUT_PATH or review.json).",
    )
    args = parser.parse_args()

    try:
        settings = Settings()
    except Exception as exc:
        print(f"Failed to load settings: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    event_path = Path(args.event_path)
    if not event_path.is_file():
        raise SystemExit("OpenHands reviewer requires --event-path or GITHUB_EVENT_PATH pointing to a pull_request payload.")

    review = run_openhands_backend(settings, event_path)

    try:
        Path(args.output_path).write_text(json.dumps(review.model_dump(), indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"Failed to write agent output to {args.output_path}: {exc}") from exc


if __name__ == "__main__":
    main()
