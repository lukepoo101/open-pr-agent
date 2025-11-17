# Open PR Agent

FOSS AI PR review agent

## Quickstart

1. Install dependencies with `uv sync`.
2. Export the OpenAI-compatible connection details (or place them in a `.env` file):
   - `OPENAI_BASE_URL`: HTTPS endpoint for your custom model gateway.
   - `OPENAI_MODEL`: Model identifier (e.g. `gpt-4o-mini`).
   - `OPENAI_API_KEY`: API token that grants access to the gateway.
3. Provide a pull_request event payload: on GitHub Actions the `GITHUB_EVENT_PATH` env is already populated; locally download or craft the event JSON and pass `--event-path <pull_request.json>` (or export `GITHUB_EVENT_PATH`).
4. Run the reviewer: `uv run python main.py --event-path <pull_request.json> --output-path review.md`.

The script launches the OpenHands agent so it can explore the repository, then writes the raw Markdown review summary directly to the specified file (default `openhands-review.md`). Any missing env var or invalid event payload causes the run to exit with a helpful error.

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
          agent_output_path: review.md
```

Key inputs:

- `openai_base_url`, `openai_model`, `openai_api_key` (required): connection information for your OpenAI-compatible endpoint.
- `github_token` (optional): defaults to the workflow `GITHUB_TOKEN`. Provide a PAT/GitHub App token if you need to bypass the default permissions.
- `agent_output_path`: customize where the Markdown review is written. The workflow prints the contents so you can inspect it in the logs.

After generating the Markdown summary, the action posts it as a COMMENT review on the pull request via `gh api`. If you prefer to only inspect the file, omit the final step from your workflow.

A ready-to-use validation workflow still lives at `.github/workflows/pr-review.yml`. It exercises the action on every PR update and remains a reference implementation. Use downstream steps or manual review to interpret the generated Markdown as needed.
