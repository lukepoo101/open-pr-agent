# Open PR Agent

FOSS AI PR review agent

## Quickstart

1. Install dependencies with `uv sync`.
2. Export the OpenAI-compatible connection details (or place them in a `.env` file):
   - `OPENAI_BASE_URL`: HTTPS endpoint for your custom model gateway.
   - `OPENAI_MODEL`: Model identifier (e.g. `gpt-4o-mini`).
   - `OPENAI_API_KEY`: API token that grants access to the gateway.
3. Run the reviewer: `uv run python main.py`.

The script gathers `git diff origin/main`, creates an `OpenAIProvider` using your base URL + key, and feeds the diff to a Pydantic AI agent configured to surface review feedback. Any missing env var or git failure causes the run to exit with a helpful error.
