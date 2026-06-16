// Helpers for working with per-model parameter capabilities returned by the
// /api/models/available endpoint (supports_temperature, supports_reasoning_effort, reasoning_style).

export function buildModelCapabilityMap(providers) {
  const map = {};
  if (!providers) return map;
  Object.values(providers).forEach((models) => {
    (models || []).forEach((m) => {
      if (m && m.id) {
        map[m.id] = {
          supports_temperature: m.supports_temperature,
          supports_reasoning_effort: m.supports_reasoning_effort,
          reasoning_style: m.reasoning_style,
        };
      }
    });
  });
  return map;
}

export function getModelCapabilities(map, modelId) {
  if (!map || !modelId) return null;
  return map[modelId] || map[modelId.replace(/^azure\//, '')] || null;
}

// Returns true/false when known, or undefined when the model/capability is unknown
// (callers should treat undefined as "don't lock" to avoid false negatives).
export function getModelCapability(map, modelId, capabilityKey) {
  const caps = getModelCapabilities(map, modelId);
  if (!caps) return undefined;
  return caps[capabilityKey];
}

export function capabilityLockMessage(capabilityKey, modelId) {
  const name = modelId || 'the selected model';
  if (capabilityKey === 'supports_temperature') {
    return `${name} doesn't support a custom temperature (it's deprecated for this model), so this value is ignored.`;
  }
  if (capabilityKey === 'supports_reasoning_effort') {
    return `${name} doesn't support a reasoning level, so this value is ignored.`;
  }
  return `${name} doesn't support this parameter, so this value is ignored.`;
}
