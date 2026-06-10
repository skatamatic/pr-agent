import React, { useMemo, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useAvailableModels } from '../hooks/useAvailableModels';

const PROVIDER_STATUS_LABELS = {
  configured: 'Connected',
  no_key: 'No API key',
};

const ModelCombobox = ({
  label,
  value,
  onChange,
  description,
  disabled = false,
  allowEmpty = false,
  emptyLabel = 'Select a model...',
  showRefresh = true,
  showProviderStatus = false,
  className = '',
}) => {
  const { providers, allIds, providerErrors, providerStatus, loading, error, refresh } = useAvailableModels();
  const [open, setOpen] = useState(false);
  const [inputValue, setInputValue] = useState(value || '');
  const debounceRef = useRef(null);

  React.useEffect(() => {
    setInputValue(value || '');
  }, [value]);

  React.useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  const suggestions = useMemo(() => {
    const needle = (inputValue || '').toLowerCase();
    const entries = [];
    Object.entries(providers).forEach(([group, models]) => {
      (models || []).forEach((model) => {
        const id = typeof model === 'string' ? model : model.id;
        const source = typeof model === 'string' ? 'litellm' : model.source;
        if (!id) return;
        if (!needle || id.toLowerCase().includes(needle)) {
          entries.push({ id, group, source: source || 'litellm' });
        }
      });
    });
    if (value && !entries.some((entry) => entry.id === value)) {
      entries.unshift({ id: value, group: 'Custom', source: 'custom' });
    }
    entries.sort((a, b) => {
      const liveRank = (entry) => (entry.source === 'live' ? 0 : entry.source === 'custom' ? 1 : 2);
      const rankDiff = liveRank(a) - liveRank(b);
      if (rankDiff !== 0) return rankDiff;
      return a.id.localeCompare(b.id);
    });
    return entries.slice(0, 50);
  }, [providers, inputValue, value]);

  const commitValue = (next) => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    onChange(next);
  };

  const handleInputChange = (event) => {
    const next = event.target.value;
    setInputValue(next);
    setOpen(true);
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      onChange(next);
    }, 350);
  };

  const handleBlur = () => {
    setTimeout(() => setOpen(false), 150);
    if (inputValue !== (value || '')) {
      commitValue(inputValue);
    }
  };

  const handleSelect = (modelId) => {
    setInputValue(modelId);
    commitValue(modelId);
    setOpen(false);
  };

  const isCustom = value && !allIds.includes(value);
  const inputPaddingClass = showRefresh ? 'pr-10' : '';

  const statusMessages = showProviderStatus
    ? Object.entries(providerStatus || {})
        .map(([provider, status]) => {
          const labelText = PROVIDER_STATUS_LABELS[status] || status;
          const err = providerErrors?.[provider];
          if (err) {
            return `${provider}: list failed (${err})`;
          }
          return `${provider}: ${labelText}`;
        })
    : [];

  return (
    <div className={`space-y-2 ${className}`}>
      {label && (
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          {label}
          {description && (
            <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal">{description}</span>
          )}
        </label>
      )}
      <div className="relative">
        <input
          type="text"
          value={inputValue}
          onChange={handleInputChange}
          onFocus={() => setOpen(true)}
          onBlur={handleBlur}
          disabled={disabled}
          placeholder={
            loading
              ? 'Loading models...'
              : allowEmpty
                ? emptyLabel
                : 'Type or select a model...'
          }
          className={`w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed ${inputPaddingClass}`}
        />
        {showRefresh && (
          <button
            type="button"
            onClick={() => refresh()}
            disabled={disabled || loading}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 disabled:opacity-50"
            title="Refresh model list"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        )}
        {open && suggestions.length > 0 && !disabled && !loading && (
          <div className="absolute z-20 mt-1 w-full max-h-56 overflow-auto rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg">
            {suggestions.map((entry) => (
              <button
                key={`${entry.group}-${entry.id}`}
                type="button"
                className="w-full text-left px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => handleSelect(entry.id)}
              >
                <span className="font-medium">{entry.id}</span>
                <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">{entry.group}</span>
                {entry.source === 'live' && (
                  <span className="ml-2 text-xs text-green-600 dark:text-green-400">live</span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
      {loading && (
        <p className="text-xs text-gray-500 dark:text-gray-400">Loading available models...</p>
      )}
      {isCustom && (
        <p className="text-xs text-amber-600 dark:text-amber-400">Custom model (not in discovered catalog)</p>
      )}
      {statusMessages.length > 0 && (
        <div className="text-xs text-gray-500 dark:text-gray-400 space-y-0.5">
          {statusMessages.map((msg) => (
            <p key={msg}>{msg}</p>
          ))}
        </div>
      )}
      {error && (
        <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
      )}
    </div>
  );
};

export default ModelCombobox;
