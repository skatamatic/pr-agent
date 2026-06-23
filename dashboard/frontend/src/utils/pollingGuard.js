/** Helpers to avoid false-positive polling errors when the tab is backgrounded. */

export const POLLING_ERROR_GRACE_MS = 5000;
export const TRANSIENT_FAILURE_THRESHOLD = 2;

export function isPageHidden() {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden';
}

export function isTransientClientError(error) {
  if (!error) return false;
  const code = error.code || '';
  const message = (error.message || '').toLowerCase();
  if (code === 'ECONNABORTED' || code === 'ERR_NETWORK' || code === 'ERR_CANCELED') {
    return true;
  }
  if (message.includes('timeout') || message.includes('network error')) {
    return true;
  }
  // No HTTP response usually means the browser dropped or delayed the request.
  return !error.response;
}

export function createPollingFailureTracker() {
  const counts = {};
  let visibleSince = Date.now();

  return {
    markVisible() {
      visibleSince = Date.now();
      Object.keys(counts).forEach((key) => {
        counts[key] = 0;
      });
    },
    markHidden() {
      Object.keys(counts).forEach((key) => {
        counts[key] = 0;
      });
    },
    recordSuccess(key) {
      counts[key] = 0;
    },
    shouldReportFailure(key, error) {
      if (isPageHidden()) return false;
      if (Date.now() - visibleSince < POLLING_ERROR_GRACE_MS) return false;

      const prev = counts[key] || 0;
      const next = prev + 1;
      counts[key] = next;

      if (!isTransientClientError(error)) {
        return next >= 1;
      }
      return next >= TRANSIENT_FAILURE_THRESHOLD;
    },
  };
}
