from __future__ import annotations

import json
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


def git_diff() -> str:
    """Return the diff between the working tree and origin/main."""
    try:
        result = subprocess.run(
            ["git", "diff", "origin/main"],
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
        return "No changes detected between the working tree and origin/main."
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


def run_agent() -> None:
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
            "\n- comments should cite specific files/lines with concise guidance"
            "\n- ignore formatting, linting, or stylistic issues; dedicated linters handle those"
            "\n- only flag correctness, logical flow, security, or missing critical tests/docs"
            "\n- consider the existing repo structure when deciding if new tests/docs are required"
            "\nIf no substantive issues remain, approve the diff."
        ),
    )

    diff_text = git_diff()
    tracked_files = git_tracked_files()
    prompt = (
        "Repository file list (git tracked):\n"
        f"{tracked_files}\n\n"
        "Review the following git diff between the working tree and origin/main.\n"
        "Highlight potential issues and state whether to approve or request changes.\n\n"
        f"{diff_text}"
    )

    result = agent.run_sync(prompt)
    print(json.dumps(result.output.model_dump(), indent=2))


def main() -> None:
    run_agent()


if __name__ == "__main__":
    main()
