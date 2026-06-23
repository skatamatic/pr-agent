import {
  createPollingFailureTracker,
  isPageHidden,
  isTransientClientError,
} from '../utils/pollingGuard';

describe('pollingGuard', () => {
  describe('isTransientClientError', () => {
    it('detects axios timeouts', () => {
      expect(isTransientClientError({ code: 'ECONNABORTED', message: 'timeout of 10000ms exceeded' })).toBe(true);
    });

    it('detects network errors without a response', () => {
      expect(isTransientClientError({ code: 'ERR_NETWORK', message: 'Network Error' })).toBe(true);
    });

    it('does not treat HTTP 401 as transient', () => {
      expect(isTransientClientError({ response: { status: 401 }, message: 'Request failed with status code 401' })).toBe(false);
    });
  });

  describe('createPollingFailureTracker', () => {
    beforeEach(() => {
      jest.useFakeTimers();
      jest.setSystemTime(new Date('2026-06-16T12:00:00Z'));
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    it('requires consecutive transient failures before reporting', () => {
      const tracker = createPollingFailureTracker();
      tracker.markVisible();
      jest.advanceTimersByTime(6000);
      const err = { code: 'ECONNABORTED', message: 'timeout of 10000ms exceeded' };

      expect(tracker.shouldReportFailure('operations', err)).toBe(false);
      expect(tracker.shouldReportFailure('operations', err)).toBe(true);
    });

    it('resets counts after markVisible', () => {
      const tracker = createPollingFailureTracker();
      tracker.markVisible();
      jest.advanceTimersByTime(6000);
      const err = { code: 'ECONNABORTED', message: 'timeout' };

      tracker.shouldReportFailure('health', err);
      tracker.shouldReportFailure('health', err);
      tracker.markVisible();
      jest.advanceTimersByTime(6000);

      expect(tracker.shouldReportFailure('health', err)).toBe(false);
    });

    it('does not report while page is hidden', () => {
      const tracker = createPollingFailureTracker();
      Object.defineProperty(document, 'visibilityState', {
        configurable: true,
        get: () => 'hidden',
      });

      expect(isPageHidden()).toBe(true);
      expect(
        tracker.shouldReportFailure('operations', { code: 'ECONNABORTED', message: 'timeout' })
      ).toBe(false);

      Object.defineProperty(document, 'visibilityState', {
        configurable: true,
        get: () => 'visible',
      });
    });
  });
});
