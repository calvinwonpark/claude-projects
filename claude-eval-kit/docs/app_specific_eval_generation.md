# App-Specific Eval Case Generation

## Why Tailored Eval Generation Matters

Generic eval suites test general capabilities, but they miss the specific behaviors, edge cases, and failure modes unique to your application. A founder copilot needs to route to the right agent, invoke the right tools, cite the right documents, and refuse the right requests — all within the context of *its* specific agents, tools, and knowledge base.

App-specific eval generation lets you:

- **Test real routing logic** against your actual agents (tech, marketing, investor) rather than abstract categories
- **Validate tool invocation** against your actual tools (market_size_lookup, unit_economics_calculator) rather than hypothetical ones
- **Verify RAG quality** against your actual document corpus rather than generic FAQ data
- **Catch safety gaps** specific to your app's domain and constraints
- **Scale eval coverage** without manually writing hundreds of test cases

The LLM helps *generate candidate cases*, but the system validates them deterministically. The LLM never becomes the source of truth — your app spec is.

## How App Specs Work

An app spec is a YAML file that describes everything the generator needs to know about your app:

```yaml
app_name: founder-copilot
app_description: AI copilot for startup founders...

agents:
  - tech
  - marketing
  - investor

tools:
  - market_size_lookup
  - competitor_summary
  - unit_economics_calculator

docs:
  - doc:tech/api_design.md
  - doc:marketing/customer_acquisition.md
  - doc:investor/fundraising_strategy.md
  # ... more docs

supported_categories:
  - routing
  - tool
  - rag
  - safety
  - quality

constraints:
  - Must refuse requests for data not in the knowledge base
  - Must cite sources when answering from documents
  # ... more constraints

example_prompts:
  - "What's the best API design pattern for a B2B SaaS?"
  # ... more examples
```

The generator uses this spec to:
1. Constrain the LLM to only reference known agents, tools, and docs
2. Validate every generated case against the inventory
3. Reject cases that invent capabilities

Place app specs at: `cases/apps/<app_name>/app_spec.yaml`

## How to Generate Candidate Suites

### Prerequisites

```bash
# Install the eval kit (from the project root)
pip install -e .

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...
```

### Basic Usage

```bash
# Generate 10 routing cases
python -m evalkit.generators.generate_cases \
  --app-spec cases/apps/founder_copilot/app_spec.yaml \
  --category routing \
  --count 10 \
  --out cases/apps/founder_copilot/generated/routing.jsonl

# Generate 20 tool use cases
python -m evalkit.generators.generate_cases \
  --app-spec cases/apps/founder_copilot/app_spec.yaml \
  --category tool \
  --count 20 \
  --out cases/apps/founder_copilot/generated/tool_use.jsonl

# Generate all categories
for cat in routing tool rag safety quality; do
  python -m evalkit.generators.generate_cases \
    --app-spec cases/apps/founder_copilot/app_spec.yaml \
    --category $cat \
    --count 15 \
    --out cases/apps/founder_copilot/generated/${cat}.jsonl \
    --overwrite
done
```

### CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--app-spec` | (required) | Path to app spec YAML |
| `--category` | (required) | Category to generate: routing, tool, rag, safety, quality |
| `--count` | 10 | Number of cases to generate |
| `--out` | (none) | Output JSONL file path. If omitted, prints to stdout |
| `--model` | claude-sonnet-4-5-20250929 | Claude model to use |
| `--temperature` | 0.7 | Sampling temperature (higher = more diverse) |
| `--seed` | (none) | Seed for prompt variation |
| `--dry-run` | false | Print the prompt without calling the API |
| `--print-prompt` | false | Print the prompt before calling the API |
| `--overwrite` | false | Overwrite output file instead of appending |

### Dry Run (Preview Prompts)

```bash
python -m evalkit.generators.generate_cases \
  --app-spec cases/apps/founder_copilot/app_spec.yaml \
  --category routing \
  --count 5 \
  --dry-run
```

This prints the full system and user prompt without making any API calls. Useful for reviewing and tuning prompts before spending API credits.

## How to Review and Promote Generated Cases

### Review Workflow

1. **Generate** candidate cases to the `generated/` directory
2. **Review** the JSONL file — each line is a self-contained JSON object
3. **Edit** individual cases as needed (fix prompts, adjust expectations, add notes)
4. **Promote** reviewed cases to the `canonical/` directory

### What to Look For

- **Prompt quality**: Is it realistic? Would a real user ask this?
- **Expectations accuracy**: Is the expected agent/tool/doc correct?
- **Edge case coverage**: Are ambiguous and boundary cases represented?
- **Difficulty distribution**: Is there a mix of easy, medium, and hard?
- **Duplicate prompts**: Are there near-duplicates that should be removed?

### Promoting to Canonical

Once reviewed, copy or move validated cases:

```bash
# Copy reviewed cases to canonical
cp cases/apps/founder_copilot/generated/routing.jsonl \
   cases/apps/founder_copilot/canonical/routing.jsonl
```

The `canonical/` directory holds reviewed, human-approved suites. The `generated/` directory holds raw LLM output that may still need review.

## How to Run Generated Suites

Generated and canonical suites are standard JSONL files, fully compatible with the existing eval runner:

```bash
# Run a generated suite in offline mode
evalkit run --suite cases/apps/founder_copilot/generated/routing.jsonl --mode offline

# Run a canonical suite against your app
evalkit run \
  --suite cases/apps/founder_copilot/canonical/tool_use.jsonl \
  --mode offline \
  --adapter http

# Run with limited cases for quick testing
evalkit run \
  --suite cases/apps/founder_copilot/generated/rag.jsonl \
  --mode offline \
  --max-cases 5
```

## Directory Structure

```
cases/apps/founder_copilot/
├── app_spec.yaml                  # App description and inventory
├── generated/                     # Raw LLM-generated suites
│   ├── routing.jsonl
│   ├── tool_use.jsonl
│   ├── rag.jsonl
│   ├── safety.jsonl
│   └── quality.jsonl
└── canonical/                     # Reviewed and promoted suites
    └── (copy reviewed suites here)
```

## Adding a New App

1. Create `cases/apps/<your_app>/app_spec.yaml`
2. Fill in agents, tools, docs, categories, and constraints
3. Run the generator for each category
4. Review and promote to canonical
5. Run with the eval runner

The generator is not hardcoded to any specific app — it reads everything from the app spec.

## Validation

Every generated case is validated before writing:

- **Category**: Must be in `supported_categories`
- **Agent**: `expected_agent` must be in the `agents` list
- **Tools**: Each tool in `expected_tools` must be in the `tools` list
- **Docs**: Each doc in `gold_doc_ids` must be in the `docs` list
- **IDs**: Must be unique (no duplicates within file or batch)
- **Prompts**: Near-duplicate prompts (>85% similarity) get a warning
- **Required fields**: id, category, input.prompt must be present

Invalid cases are logged with clear reasons and excluded from the output file.
