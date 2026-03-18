# Jira Bug → Cursor Prompt

A lightweight internal tool that converts Jira bug reports into structured debugging prompts for Cursor.

## How it works

1. Enter a Jira issue key
2. The app fetches bug details (mock data by default)
3. Normalizes the raw Jira data into a clean shape
4. Detects relevant product domains from the bug fields
5. Loads company-specific debugging knowledge from markdown docs in the repo
6. Sends everything to Claude to generate a Cursor-ready debugging prompt
7. Displays the prompt with a copy-to-clipboard button

## Setup

```bash
cd jira-bug-cursor-prompt

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Run

```bash
# Mock Jira mode (default — no API key needed for basic functionality)
uvicorn app.main:app --reload --port 8000

# With Claude integration
ANTHROPIC_API_KEY=sk-ant-... uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 and try issue key **DR-1042**.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `USE_MOCK_JIRA` | `true` | Use mock Jira data instead of real API |
| `ANTHROPIC_API_KEY` | _(empty)_ | Anthropic API key for Claude |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Claude model to use |

If `ANTHROPIC_API_KEY` is not set, the app falls back to a deterministic local prompt builder so it still runs without any external dependencies.

## Adding company knowledge

Knowledge docs live in `docs/` as markdown files:

```
docs/
  domains/           # Domain-specific context
    digital-rooms.md
    pitch-data.md
  debug-playbooks/   # Step-by-step debugging guides
    digital-rooms.md
```

To add a new domain:

1. Create the markdown doc(s) in `docs/`
2. Add a keyword rule to `app/services/detect_domain.py`
3. Map the domain ID to doc paths in `app/services/company_knowledge.py`

## Project structure

```
app/
  main.py                          # FastAPI routes
  config.py                        # Environment config
  models/                          # Pydantic models
    jira.py / bug.py / knowledge.py
  services/                        # Business logic
    jira_client.py                 # Jira abstraction
    mock_jira.py                   # Mock data
    normalize_bug.py               # Raw → normalized
    detect_domain.py               # Domain detection heuristics
    company_knowledge.py           # Domain → doc path mapping
    load_knowledge.py              # Markdown doc loader
    claude_prompt_generator.py     # Claude integration + fallback
  templates/
    index.html                     # UI
docs/                              # Company knowledge (markdown)
```
