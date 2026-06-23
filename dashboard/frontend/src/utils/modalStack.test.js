import {
  acquireModalLock,
  isTopModal,
  releaseModalLock,
  resetModalStackForTests,
} from './modalStack';

describe('modalStack', () => {
  beforeEach(() => {
    resetModalStackForTests();
  });

  it('locks body scroll on first acquire and restores after last release', () => {
    document.body.style.overflow = 'scroll';

    acquireModalLock('modal-a');
    expect(document.body.style.overflow).toBe('hidden');

    acquireModalLock('modal-b');
    expect(document.body.style.overflow).toBe('hidden');

    releaseModalLock('modal-a');
    expect(document.body.style.overflow).toBe('hidden');

    releaseModalLock('modal-b');
    expect(document.body.style.overflow).toBe('scroll');
  });

  it('tracks topmost modal for Escape handling', () => {
    acquireModalLock('modal-a');
    acquireModalLock('modal-b');

    expect(isTopModal('modal-a')).toBe(false);
    expect(isTopModal('modal-b')).toBe(true);

    releaseModalLock('modal-b');
    expect(isTopModal('modal-a')).toBe(true);
  });

  it('removes modal from stack when closed out of order', () => {
    acquireModalLock('modal-a');
    acquireModalLock('modal-b');

    releaseModalLock('modal-a');
    expect(isTopModal('modal-b')).toBe(true);
  });
});
