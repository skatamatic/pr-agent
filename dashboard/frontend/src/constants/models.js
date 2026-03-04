/**
 * Centralized model catalog for the PR-Agent dashboard.
 *
 * All dashboard components (ConfigEditor, PrAgentConfigEditor, MetricsView)
 * import from here so the supported model list stays consistent and easy to
 * update when providers release new versions.
 *
 * Each entry carries the litellm-compatible model ID, a human-friendly
 * display name, the provider, and a tier used by the metrics cost UI.
 */

const MODEL_CATALOG = [
  // ── Anthropic ──────────────────────────────────────────────
  {
    id: 'anthropic/claude-opus-4-6-20260205',
    name: 'Claude Opus 4.6',
    provider: 'anthropic',
    tier: 'premium',
  },
  {
    id: 'anthropic/claude-sonnet-4-6-20260205',
    name: 'Claude Sonnet 4.6',
    provider: 'anthropic',
    tier: 'standard',
  },
  {
    id: 'anthropic/claude-haiku-4-5-20251001',
    name: 'Claude Haiku 4.5',
    provider: 'anthropic',
    tier: 'budget',
  },

  // ── Google Gemini ──────────────────────────────────────────
  {
    id: 'gemini/gemini-3.1-pro-preview',
    name: 'Gemini 3.1 Pro',
    provider: 'google',
    tier: 'premium',
  },
  {
    id: 'gemini/gemini-3-flash-preview',
    name: 'Gemini 3 Flash',
    provider: 'google',
    tier: 'budget',
  },

  // ── OpenAI ─────────────────────────────────────────────────
  {
    id: 'gpt-5',
    name: 'GPT-5',
    provider: 'openai',
    tier: 'premium',
  },
  {
    id: 'gpt-5-mini',
    name: 'GPT-5 Mini',
    provider: 'openai',
    tier: 'budget',
  },
  {
    id: 'gpt-5.3-codex',
    name: 'GPT-5.3 Codex',
    provider: 'openai',
    tier: 'premium',
  },
  {
    id: 'gpt-5.3-codex-spark',
    name: 'GPT-5.3 Codex Spark',
    provider: 'openai',
    tier: 'budget',
  },
];

// ── Derived helpers ────────────────────────────────────────────

/** Flat array of all model ID strings. */
export const ALL_MODEL_IDS = MODEL_CATALOG.map((m) => m.id);

/**
 * Models grouped by provider – used for <optgroup> dropdowns.
 *
 * Shape: { anthropic: [...ids], google: [...ids], openai: [...ids] }
 */
export const MODELS_BY_PROVIDER = MODEL_CATALOG.reduce((acc, m) => {
  const label =
    m.provider === 'anthropic'
      ? 'Anthropic'
      : m.provider === 'google'
        ? 'Google'
        : 'OpenAI';
  if (!acc[label]) acc[label] = [];
  acc[label].push(m.id);
  return acc;
}, {});

/**
 * Models grouped by tier – used for the MetricsView cost-configuration tabs.
 *
 * Shape: { premium: [...ids], standard: [...ids], budget: [...ids] }
 */
export const MODELS_BY_TIER = MODEL_CATALOG.reduce((acc, m) => {
  const label =
    m.tier === 'premium'
      ? 'Premium'
      : m.tier === 'standard'
        ? 'Standard'
        : 'Budget';
  if (!acc[label]) acc[label] = [];
  acc[label].push(m.id);
  return acc;
}, {});

/** Lookup map: model ID → display name. */
export const MODEL_DISPLAY_NAMES = Object.fromEntries(
  MODEL_CATALOG.map((m) => [m.id, m.name])
);

/**
 * Default per-1K-token costs (USD) for each model.
 * These are used as initial values in the MetricsView pricing configuration
 * and as backend defaults in metrics_service.py (keep them in sync).
 */
export const DEFAULT_MODEL_COSTS = {
  'anthropic/claude-opus-4-6-20260205':   { input: 0.005,    output: 0.025    },
  'anthropic/claude-sonnet-4-6-20260205': { input: 0.003,    output: 0.015    },
  'anthropic/claude-haiku-4-5-20251001':  { input: 0.00025,  output: 0.00125  },
  'gemini/gemini-3.1-pro-preview':        { input: 0.0035,   output: 0.0105   },
  'gemini/gemini-3-flash-preview':        { input: 0.000075, output: 0.0003   },
  'gpt-5':                                 { input: 0.00125,  output: 0.01     },
  'gpt-5-mini':                            { input: 0.00025,  output: 0.002    },
  'gpt-5.3-codex':                        { input: 0.00175,  output: 0.014    },
  'gpt-5.3-codex-spark':                  { input: 0.001,    output: 0.008    },
};

export default MODEL_CATALOG;
