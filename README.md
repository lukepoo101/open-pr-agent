# Open PR Agent

FOSS AI PR review agent

## Quickstart

1. Install dependencies with `uv sync`.
2. Export the OpenAI-compatible connection details (or place them in a `.env` file):
   - `OPENAI_BASE_URL`: HTTPS endpoint for your custom model gateway.
   - `OPENAI_MODEL`: Model identifier (e.g. `gpt-4o-mini`).
   - `OPENAI_API_KEY`: API token that grants access to the gateway.
3. (Optional) Set `OPEN_PR_AGENT_BASE_REF` or pass `--base-ref <git ref>` if you need to diff against something other than `origin/main`.
4. Run the reviewer: `uv run python main.py` (add `--base-ref` if desired).

The script gathers `git diff origin/main`, creates an `OpenAIProvider` using your base URL + key, and feeds the diff to a Pydantic AI agent configured to surface review feedback. Any missing env var or git failure causes the run to exit with a helpful error.

## GitHub Action

A ready-to-use workflow lives at `.github/workflows/pr-review.yml`. It runs on every PR update and posts an approval or change request using the agent's structured output. To enable it:

1. In **Settings → Secrets and variables → Actions**, add repository variables `OPENAI_BASE_URL` and `OPENAI_MODEL` plus a secret `OPENAI_API_KEY`.
2. Commit the workflow (already in this repo) and ensure the `GITHUB_TOKEN` has `pull-requests: write` (set via workflow permissions).
3. When a PR is opened or updated, the workflow fetches full history, runs `uv run main.py --base-ref origin/<target-branch>`, transforms the JSON via `scripts/post_review.py`, and calls the GitHub Reviews API to leave the summary and inline comments as the workflow bot user.
