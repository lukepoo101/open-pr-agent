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
- `base_ref` (optional): override the default `origin/<PR base>` comparison.
- `allow_approvals` (optional): defaults to `false`, set to `true` only when the supplied token may approve reviews.
- `agent_output_path` / `payload_output_path`: customize where the intermediate JSON artifacts are written.

Outputs expose the generated review payload (`review-event`, `review-body`, and both file paths) so downstream steps can introspect results without re-reading the files.

A ready-to-use validation workflow still lives at `.github/workflows/pr-review.yml`. It exercises the action on every PR update and remains a reference implementation.

> ℹ️ GitHub Actions tokens cannot approve PRs. By default the action downgrades an `APPROVE` decision to a comment and adds a note explaining why. Provide a PAT/GitHub App token via `github_token` and set `allow_approvals=true` if approvals should be forwarded.
