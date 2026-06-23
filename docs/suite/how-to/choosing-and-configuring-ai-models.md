# Choosing and configuring AI models

Model selection, dashboard setup, and syncing changes to Azure DevOps pipelines.

## Model roles

The **AI Models** tab exposes four primary roles:

| UI label | Typical use |
|----------|-------------|
| **Default Model** | Describe, review, improve: main quality path |
| **Reasoning Model** | Self-reflection and deeper analysis when enabled |
| **Simple/Budget Model** | Cheaper path for lighter work (including descriptions) |
| **Fallback models** (**Advanced** tab) | Ordered retries when the primary model errors or rate-limits |

**Time Estimation** tab: optional **Override Model** for the time-saved second pass (defaults to the primary model).

Per-tool overrides: **PR-Agent Config** → **Models** or the tool section (**PR Reviewer**, **Code Suggestions**, etc.).

Supported catalog (maintained in dashboard): Anthropic Claude Opus/Sonnet/Haiku, Google Gemini Pro/Flash, OpenAI GPT 5.x and Codex variants. Pick from the dropdown or enter a custom LiteLLM ID where supported.

## Global configuration (AI Config)

1. Dashboard → **AI Config** → **AI Models** tab.
2. Set **Default**, **Reasoning**, and **Simple/Budget** models.
3. Enter API keys in the same tab (**OpenAI**, **Anthropic**, **Google**, etc.).
4. Adjust **temperature** and **reasoning effort** when the model supports them. Unsupported controls are locked with a tooltip.
5. **Advanced** tab → **Fallback models** for ordered retry list.
6. **Save**.

### Verify before syncing to pipelines

- **Test Model** on **AI Models**: confirms keys and model ID against the provider.
- **Test Connection** on **Code Context**: separate from LLM; run if you use the C# context service.

## Sync keys and URLs to Azure DevOps

Saving **AI Config** updates global storage. Pipeline containers still need matching **pipeline variables**:

1. **Repositories** → repo card → **Azure Pipeline** → **Fix Issues**.
2. Fix Issues pushes YAML, syncs keys, dashboard URL, and related vars, and repairs build validation.

Without Fix Issues after a key rotation, runs fail with auth errors even when **AI Config** looks correct.

## Per-repository model overrides

When one team needs a different model:

1. **Repositories** → **PR-Agent Config** → **Models** section.
2. Override only the fields that differ (blue highlight = differs from global).
3. **Save** → merge the config PR.

**View Effective Config** shows override-focused summary.

## Choosing models in practice

| Goal | Suggestion |
|------|------------|
| Best review quality | Default: Claude Sonnet or Opus; enable reasoning model for self-reflection |
| Lowest cost | Default: Haiku or GPT Codex Spark; disable improve on noisy repos (see [Configuration and overrides](configuration-and-overrides.md)) |
| Large monorepos | Cap diff size with [PR filters](configuring-pr-filters.md); use Sonnet over Opus |
| Rate limits | Configure **Fallback models** in **AI Config → Advanced** |

## Propagation timeline

| Change | When it applies |
|--------|-----------------|
| AI Config save | Next **new** pipeline run |
| PR-Agent Config merge | Same run, after repo settings load |
| Pipeline variable sync | Next run after **Fix Issues** |

## Troubleshooting

| Symptom | Check |
|---------|-------|
| 401 / invalid key | AI Config keys → **Test Model** → **Fix Issues** |
| Model not in dropdown | Use custom LiteLLM ID; confirm provider prefix |
| Temperature ignored | Model may not support it: UI shows lock |
| Old model still used | New pipeline run required |
| Per-repo override ignored | Config PR merged? **View Effective Config** |

See [Maintenance troubleshooting](maintenance/troubleshooting.md) for the three-layer key diagnostic flow.

Model registry behavior: [Technical internals](../technical/internals/README.md).
