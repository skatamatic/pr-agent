import React, { useMemo, useState } from 'react';
import { X } from 'lucide-react';
import { useAvailableModels } from '../hooks/useAvailableModels';

const ModelMultiCombobox = ({
  label,
  value = [],
  onChange,
  description,
  disabled = false,
}) => {
  const { providers } = useAvailableModels();
  const [draft, setDraft] = useState('');
  const selected = Array.isArray(value) ? value : [];

  const options = useMemo(() => {
    const ids = new Set();
    Object.values(providers).forEach((models) => {
      (models || []).forEach((model) => {
        const id = typeof model === 'string' ? model : model.id;
        if (id) ids.add(id);
      });
    });
    selected.forEach((id) => ids.add(id));
    return Array.from(ids).sort();
  }, [providers, selected]);

  const addModel = (modelId) => {
    const trimmed = (modelId || '').trim();
    if (!trimmed || selected.includes(trimmed)) return;
    onChange([...selected, trimmed]);
    setDraft('');
  };

  const removeModel = (modelId) => {
    onChange(selected.filter((item) => item !== modelId));
  };

  return (
    <div className="space-y-2">
      {label && (
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          {label}
          {description && (
            <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal">{description}</span>
          )}
        </label>
      )}
      <div className="flex flex-wrap gap-2 mb-2">
        {selected.map((modelId) => (
          <span
            key={modelId}
            className="inline-flex items-center gap-1 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200 px-2 py-1 text-xs"
          >
            {modelId}
            {!disabled && (
              <button type="button" onClick={() => removeModel(modelId)} className="hover:text-blue-600">
                <X className="h-3 w-3" />
              </button>
            )}
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              addModel(draft);
            }
          }}
          disabled={disabled}
          placeholder="Type model id and press Enter"
          list="fallback-model-options"
          className="flex-1 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
        />
        <button
          type="button"
          disabled={disabled || !draft.trim()}
          onClick={() => addModel(draft)}
          className="px-3 py-2 text-sm rounded-md bg-primary-600 text-white disabled:opacity-50"
        >
          Add
        </button>
      </div>
      <datalist id="fallback-model-options">
        {options.map((modelId) => (
          <option key={modelId} value={modelId} />
        ))}
      </datalist>
    </div>
  );
};

export default ModelMultiCombobox;
