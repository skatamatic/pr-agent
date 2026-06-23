# Config, AI, and filters

## Configuration loading

### Import time (`pr_agent/config_loader.py`)

1. Package TOML files (configuration, prompts, ignore, etc.)
2. Overlay from `PR_AGENT_CONFIG_PATH` **or** GCS download (5 files)
3. Pipeline env overrides in `run_action()` (PAT, org, provider, keys, `AUTO_*`)

> **Local CLI only:** `[tool.pr-agent]` in `pyproject.toml` may merge at import when cwd is inside a git checkout. Not used on standard Azure Docker runs.

### Per-PR (`apply_repo_settings`)

1. Respect `use_repo_settings_file`
2. Fetch `.pr_agent.toml` from PR repo via git provider
3. Dynaconf merge into runtime settings

Full hierarchy: [Configuration and overrides](../../how-to/configuration-and-overrides.md), [TOML configuration system](../toml-configuration-system.md).

## LiteLLM

**Handler:** `pr_agent/algo/ai_handlers/litellm_ai_handler.py`

- **Registry:** `pr_agent/algo/model_registry.py`: temperature and reasoning per model
- **Fallback:** `retry_with_fallback_models()` in `pr_agent/algo/pr_processing.py`
- **Parameter negotiation**: drops unsupported params on `BadRequestError`

[Choosing and configuring AI models](../../how-to/choosing-and-configuring-ai-models.md).

## PR filters

**File:** `pr_agent/algo/pr_filters.py`

Evaluated per command after repo settings. Settings from `[pr_filters]` in deployment or repo TOML.

| Filter | Skip | Terminate |
|--------|------|-----------|
| `skip_if_description_exists` | describe when PR body non-empty | - |
| `terminate_on_no_bots` | - | `[no_bots]` / `[nobots]` in description |
| `max_lines_changed` | - | diff over line limit |
| `skip_if_review_suggestions_exist` | prior PR-Agent output detected | - |

If `[pr_filters]` is missing or empty, all checks are skipped.

**Not the same as:** `[config].ignore_pr_*` (webhook-only on GitHub/GitLab) or `[ignore].glob` file patterns.

[Configuring PR filters](../../how-to/configuring-pr-filters.md).

## Best practices

**File:** `pr_agent/algo/utils.py` → `get_best_practices_content()`

Called from review/improve tools only. Branch resolution matches `.pr_agent.toml`.
