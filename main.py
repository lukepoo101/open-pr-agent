from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import requests
from openhands.sdk import Conversation, LLM, get_logger
from openhands.sdk.conversation import get_agent_final_response
from openhands.tools.preset.default import get_default_agent
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = get_logger(__name__)

COMMENT_TAG = "<!-- open-pr-agent-review -->"

OPENHANDS_PROMPT = """You are an expert code reviewer. Use bash commands to analyze the PR
changes and identify issues that need to be addressed.

## Pull Request Information
- **Title**: {title}
- **Description**: {body}
- **Repository**: {repo_name}
- **Base Branch**: {base_branch}
- **Head Branch**: {head_branch}

## Analysis Process
Use bash commands to understand the changes. You should start by running:
`git diff {base_branch}...{head_branch} -- . ':(exclude)package-lock.json' ':(exclude)yarn.lock' ':(exclude)pnpm-lock.yaml' ':(exclude)poetry.lock' ':(exclude)uv.lock' ':(exclude)*.lock'`
to see the changes introduced by this PR, excluding lock files.
Then examine the code related to the PR. Ignore any other generated artifacts or compiled assets
even if the PR modifies them—focus on source files and meaningful changes only.

## Review Output Format
Provide a concise review focused on issues that need attention. If there are no issues
of a particular importance level (e.g. no critical issues), it is OK to skip that level
or even not point out any issues at all.
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
- Follow the format above strictly
- Do NOT include lengthy positive feedback

Start by analyzing the changes with bash commands, then provide your structured review.
"""


class Settings(BaseSettings):
    """Load OpenAI-compatible connection details from the environment or a .env file."""

    model_config = SettingsConfigDict(env_prefix="OPENAI_", env_file=".env", extra="ignore")

    base_url: str
    model: str
    api_key: str


def _prepare_openhands_model(model_name: str) -> str:
    model_name = model_name.strip()
    if "/" in model_name:
        return model_name
    return f"openai/{model_name}"


def _get_git_output(args: list[str]) -> str:
    try:
        return subprocess.check_output(args, text=True).strip()
    except subprocess.CalledProcessError:
        return ""


def _load_local_info() -> dict[str, str]:
    """Infer PR information from the local git repository."""
    head_branch = _get_git_output(["git", "branch", "--show-current"]) or "unknown"
    
    # Try to get repo name from remote origin
    remote_url = _get_git_output(["git", "config", "--get", "remote.origin.url"])
    repo_name = "unknown/unknown"
    if remote_url:
        # simplistic parsing for git@github.com:user/repo.git or https://github.com/user/repo.git
        if "github.com" in remote_url:
            parts = remote_url.replace(".git", "").split("/")
            if len(parts) >= 2:
                repo_name = f"{parts[-2].split(':')[-1]}/{parts[-1]}"

    return {
        "number": "local",
        "title": f"Local Review: {head_branch}",
        "body": "Local review session.",
        "repo_name": repo_name,
        "base_branch": "main",  # Default to main for local
        "head_branch": head_branch,
    }


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


def run_openhands_backend(settings: Settings, event_path: Path | None) -> str:
    if event_path:
        pr_info = _load_pr_info(event_path)
    else:
        logger.info("No event path provided, using local git context.")
        pr_info = _load_local_info()

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

    return review_content.strip()


def post_github_comment(
    review: str, pr_info: dict[str, str], token: str, delete_old_comments: bool = True
) -> None:
    if not token:
        logger.warning("No GITHUB_TOKEN provided, skipping comment posting.")
        return

    repo = pr_info["repo_name"]
    issue_number = pr_info["number"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    if delete_old_comments:
        try:
            # List comments on the issue/PR
            comments_url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
            comments_resp = requests.get(comments_url, headers=headers, params={"per_page": 100})
            comments_resp.raise_for_status()

            # Delete comments that contain the tag
            for comment in comments_resp.json():
                if COMMENT_TAG in (comment.get("body") or ""):
                    delete_url = f"https://api.github.com/repos/{repo}/issues/comments/{comment['id']}"
                    delete_resp = requests.delete(delete_url, headers=headers)
                    delete_resp.raise_for_status()
                    logger.info("Deleted old comment %s", comment["id"])
        except requests.exceptions.RequestException as exc:
            logger.warning("Failed to delete old comments: %s", exc)

    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    data = {"body": f"{review}\n\n{COMMENT_TAG}"}

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        logger.info("Successfully posted review comment to PR #%s", issue_number)
    except requests.exceptions.RequestException as exc:
        logger.error("Failed to post review comment: %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Open PR Agent reviewer.")
    parser.add_argument(
        "--event-path",
        default=os.getenv("GITHUB_EVENT_PATH", ""),
        help="Path to a pull_request event payload. Defaults to GITHUB_EVENT_PATH. If not provided, attempts to use local git context.",
    )
    parser.add_argument(
        "--output-path",
        default=os.getenv("AGENT_OUTPUT_PATH", "openhands-review.md"),
        help="Where to write the OpenHands review markdown (defaults to AGENT_OUTPUT_PATH or openhands-review.md).",
    )
    parser.add_argument(
        "--github-token",
        default=os.getenv("GITHUB_TOKEN", ""),
        help="GitHub token for posting comments (optional). Defaults to GITHUB_TOKEN.",
    )
    parser.add_argument(
        "--delete-old-comments",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether to delete old review comments from this bot. Defaults to True.",
    )
    args = parser.parse_args()

    try:
        settings = Settings()
    except Exception as exc:
        print(f"Failed to load settings: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    event_path = None
    if args.event_path:
        event_path = Path(args.event_path)
        if not event_path.is_file():
            raise SystemExit(f"Provided event path '{args.event_path}' does not exist.")

    review = run_openhands_backend(settings, event_path)

    try:
        Path(args.output_path).write_text(f"{review.strip()}\n", encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"Failed to write agent output to {args.output_path}: {exc}") from exc

    print(f"OpenHands review written to {args.output_path}")

    if event_path:
        if not args.github_token:
            logger.warning("No GITHUB_TOKEN provided. Skipping comment posting.")
        else:
            pr_info = _load_pr_info(event_path)
            post_github_comment(
                review, pr_info, args.github_token, args.delete_old_comments
            )
    elif args.github_token:
        logger.warning("Cannot post comment without event payload (local mode).")


if __name__ == "__main__":
    main()
