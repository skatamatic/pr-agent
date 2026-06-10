/**
 * Metrics-only model metadata for the dashboard.
 *
 * AI Config and per-repo override UIs load models dynamically from
 * GET /api/models/available. This file remains for MetricsView cost defaults.
 */

/** Default per-1K-token costs (USD). Keep in sync with metrics_service.default_model_costs. */
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

/** Tier assignments for known metrics models. */
export const MODEL_TIERS = {
  'anthropic/claude-opus-4-6-20260205': 'Premium',
  'anthropic/claude-sonnet-4-6-20260205': 'Standard',
  'anthropic/claude-haiku-4-5-20251001': 'Budget',
  'gemini/gemini-3.1-pro-preview': 'Premium',
  'gemini/gemini-3-flash-preview': 'Budget',
  'gpt-5': 'Premium',
  'gpt-5-mini': 'Budget',
  'gpt-5.3-codex': 'Premium',
  'gpt-5.3-codex-spark': 'Budget',
};

export const ALL_MODEL_IDS = Object.keys(DEFAULT_MODEL_COSTS);

export const MODELS_BY_TIER = ALL_MODEL_IDS.reduce((acc, modelId) => {
  const tier = MODEL_TIERS[modelId] || 'Standard';
  if (!acc[tier]) acc[tier] = [];
  acc[tier].push(modelId);
  return acc;
}, {});

export const MODEL_DISPLAY_NAMES = Object.fromEntries(
  ALL_MODEL_IDS.map((id) => [id, id.split('/').pop() || id])
);

export default DEFAULT_MODEL_COSTS;
