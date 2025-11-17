# Open PR Agent

FOSS AI PR review agent

## Quickstart

1. Install dependencies with `uv sync`.
2. Export the OpenAI-compatible connection details (or place them in a `.env` file):
   - `OPENAI_BASE_URL`: HTTPS endpoint for your custom model gateway.
   - `OPENAI_MODEL`: Model identifier (e.g. `gpt-4o-mini`).
   - `OPENAI_API_KEY`: API token that grants access to the gateway.
3. Provide a pull_request event payload: on GitHub Actions the `GITHUB_EVENT_PATH` env is already populated; locally download or craft the event JSON and pass `--event-path <pull_request.json>` (or export `GITHUB_EVENT_PATH`).
4. Run the reviewer: `uv run python main.py --event-path <pull_request.json>`.

The script launches the OpenHands agent so it can explore the repository, then post-processes its Markdown output into structured review data. Any missing env var or invalid event payload causes the run to exit with a helpful error.

## GitHub Action

This repo ships a composite action (`action.yml`) so any workflow can run the reviewer in a single step:

```yaml
jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - name: Open PR Agent
        uses: your-org/open-pr-agent@v1
        with:
          openai_base_url: ${{ vars.OPENAI_BASE_URL }}
          openai_model: ${{ vars.OPENAI_MODEL }}
          openai_api_key: ${{ secrets.OPENAI_API_KEY }}
          allow_approvals: false # Set true only if the provided token is allowed to approve PRs
```

Key inputs:

- `openai_base_url`, `openai_model`, `openai_api_key` (required): connection information for your OpenAI-compatible endpoint.
- `github_token` (optional): defaults to the workflow `GITHUB_TOKEN`, override when using a PAT/GitHub App.
- `allow_approvals` (optional): defaults to `false`, set to `true` only when the supplied token may approve reviews.
- `agent_output_path` / `payload_output_path`: customize where the intermediate JSON artifacts are written.

Outputs expose the generated review payload (`review-event`, `review-body`, and both file paths) so downstream steps can introspect results without re-reading the files.

A ready-to-use validation workflow still lives at `.github/workflows/pr-review.yml`. It exercises the action on every PR update and remains a reference implementation.

### OpenHands-powered reviews

`main.py` now orchestrates the OpenHands PR review agent under the hood. When the action runs inside GitHub Actions (where `GITHUB_EVENT_PATH` exposes the pull request payload), the workflow automatically:

1. Launches the OpenHands agent so it can explore the repository, gather diffs, and produce a Markdown review that cites file paths and line numbers for each issue whenever possible.
2. Sends that Markdown back through the structured-output agent (powered by the same `OPENAI_*` model) to convert it into `ReviewOutput` JSON.
3. Uses the existing tooling (`scripts/post_review.py`, `scripts/emit_review_outputs.py`) to build and submit rich GitHub review events with inline comments when possible.

For runs outside of GitHub Actions, remember to pass `--event-path` (or set `GITHUB_EVENT_PATH`) so the agent understands which PR to analyze. In all cases, the outputs remain identical, so downstream automation keeps working without changes.

> ℹ️ GitHub Actions tokens cannot approve PRs. By default the action downgrades an `APPROVE` decision to a comment and adds a note explaining why. Provide a PAT/GitHub App token via `github_token` and set `allow_approvals=true` if approvals should be forwarded.
