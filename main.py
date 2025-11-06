from __future__ import annotations

import subprocess
import sys

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider


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
    )

    agent = Agent(
        model=model,
        system_prompt=(
            "You are an AI pull request reviewer. Provide concise, actionable "
            "feedback on the diff you receive. Flag correctness and security "
            "risks before nitpicks."
        ),
    )

    diff_text = git_diff()
    prompt = (
        "Review the following git diff between the working tree and origin/main.\n"
        "Highlight potential issues and summarize the overall risk level.\n\n"
        f"{diff_text}"
    )

    result = agent.run_sync(prompt)
    print(result.output)


def main() -> None:
    run_agent()


if __name__ == "__main__":
    main()
