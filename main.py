from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings


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


def git_diff(base_ref: str) -> str:
    """Return the diff between the working tree and the provided base ref."""
    try:
        result = subprocess.run(
            ["git", "diff", base_ref],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise SystemExit("git command not found in PATH") from exc
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.strip() or "Failed to produce git diff.", file=sys.stderr)
        raise SystemExit(exc.returncode)

    diff = result.stdout.strip()
    if not diff:
        return f"No changes detected between the working tree and {base_ref}."
    return diff


def git_tracked_files() -> str:
    """Return the list of git-tracked files for context."""

    try:
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise SystemExit("git command not found in PATH") from exc
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.strip() or "Failed to list git files.", file=sys.stderr)
        raise SystemExit(exc.returncode)

    files = result.stdout.strip()
    if not files:
        return "<no tracked files>"
    return files


def run_agent(base_ref: str) -> None:
    try:
        settings = Settings()
    except Exception as exc:
        print(f"Failed to load settings: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    provider = OpenAIProvider(
        base_url=settings.base_url,
        api_key=settings.api_key,
    )

    model = OpenAIChatModel(
        settings.model,
        provider=provider,
        settings=ModelSettings(temperature=0.1),
    )

    agent = Agent(
        model=model,
        output_type=ReviewOutput,
        system_prompt=(
            "You are an AI pull request reviewer for GitHub. Always decide if the diff "
            "should be approved or needs changes."
            "\n- decision must be APPROVE or REQUEST_CHANGES"
            "\n- summary must be a short (<120 chars) human sentence"
            "\n- comments must cite specific files/lines with concise guidance"
            "\n- prefer line-level feedback over generic repository-wide statements"
            "\n- skip comments that cannot reference an exact file path (and line when possible)"
            "\n- ignore formatting, linting, or stylistic issues; dedicated linters handle those"
            "\n- only flag correctness, logical flow, security, or missing critical tests/docs"
            "\n- consider the existing repo structure when deciding if new tests/docs are required"
            "\n- do not restate obvious metadata (e.g., 'new files were added') unless it impacts correctness"
            "\nIf no substantive issues remain, approve the diff."
        ),
    )

    diff_text = git_diff(base_ref)
    tracked_files = git_tracked_files()
    prompt = (
        "Repository file list (git tracked):\n"
        f"{tracked_files}\n\n"
        f"Review the following git diff between the working tree and {base_ref}.\n"
        "Highlight potential issues and state whether to approve or request changes.\n\n"
        f"{diff_text}"
    )

    result = agent.run_sync(prompt)
    print(json.dumps(result.output.model_dump(), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Open PR Agent reviewer.")
    parser.add_argument(
        "--base-ref",
        default=os.getenv("OPEN_PR_AGENT_BASE_REF", "origin/main"),
        help="Git reference to diff against (default: origin/main or OPEN_PR_AGENT_BASE_REF)",
    )
    args = parser.parse_args()

    run_agent(args.base_ref)


if __name__ == "__main__":
    main()
