import { useCallback, useEffect, useState } from 'react';
import api from '../services/api';

let sharedCache = null;
let sharedPromise = null;
const subscribers = new Set();

function applyCacheData(data) {
  sharedCache = data;
  subscribers.forEach((listener) => {
    try {
      listener(data);
    } catch {
      // ignore listener errors
    }
  });
}

async function fetchModels(refresh = false) {
  if (refresh) {
    sharedCache = null;
    sharedPromise = null;
  }
  if (!refresh && sharedCache) {
    return sharedCache;
  }
  if (!refresh && sharedPromise) {
    return sharedPromise;
  }
  sharedPromise = api
    .getAvailableModels(refresh)
    .then((response) => {
      const data = response.data?.data || response.data || {};
      const payload = {
        providers: data.providers || {},
        allIds: data.all_ids || [],
        providerErrors: data.provider_errors || {},
        providerStatus: data.provider_status || {},
        fetchedAt: data.fetched_at || null,
      };
      applyCacheData(payload);
      sharedPromise = null;
      return payload;
    })
    .catch((error) => {
      sharedPromise = null;
      throw error;
    });
  return sharedPromise;
}

export function useAvailableModels() {
  const [providers, setProviders] = useState(sharedCache?.providers || {});
  const [allIds, setAllIds] = useState(sharedCache?.allIds || []);
  const [providerErrors, setProviderErrors] = useState(sharedCache?.providerErrors || {});
  const [providerStatus, setProviderStatus] = useState(sharedCache?.providerStatus || {});
  const [loading, setLoading] = useState(!sharedCache);
  const [error, setError] = useState(null);

  const syncFromCache = useCallback((data) => {
    setProviders(data.providers || {});
    setAllIds(data.allIds || []);
    setProviderErrors(data.providerErrors || {});
    setProviderStatus(data.providerStatus || {});
    setLoading(false);
    setError(null);
  }, []);

  useEffect(() => {
    subscribers.add(syncFromCache);
    if (sharedCache) {
      syncFromCache(sharedCache);
    }
    return () => {
      subscribers.delete(syncFromCache);
    };
  }, [syncFromCache]);

  const load = useCallback(async (refresh = false) => {
    if (!sharedCache || refresh) {
      setLoading(true);
    }
    setError(null);
    try {
      const data = await fetchModels(refresh);
      syncFromCache(data);
    } catch (err) {
      setError(err.message || 'Failed to load models');
      setLoading(false);
    }
  }, [syncFromCache]);

  useEffect(() => {
    if (!sharedCache) {
      load(false);
    }
  }, [load]);

  return {
    providers,
    allIds,
    providerErrors,
    providerStatus,
    loading,
    error,
    refresh: () => load(true),
  };
}

export function invalidateAvailableModelsCache() {
  sharedCache = null;
  sharedPromise = null;
}

export function __resetAvailableModelsCacheForTests() {
  sharedCache = null;
  sharedPromise = null;
  subscribers.clear();
}
