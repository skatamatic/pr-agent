/** Reference-counted modal stack for body scroll lock and Escape handling. */

let lockCount = 0;
let savedOverflow = '';
const stack = [];

export function acquireModalLock(modalId) {
  if (lockCount === 0) {
    savedOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
  }
  lockCount += 1;
  stack.push(modalId);
}

export function releaseModalLock(modalId) {
  const index = stack.lastIndexOf(modalId);
  if (index !== -1) {
    stack.splice(index, 1);
  }
  lockCount = Math.max(0, lockCount - 1);
  if (lockCount === 0) {
    document.body.style.overflow = savedOverflow;
  }
}

export function isTopModal(modalId) {
  return stack.length > 0 && stack[stack.length - 1] === modalId;
}

/** Test helper */
export function resetModalStackForTests() {
  lockCount = 0;
  savedOverflow = '';
  stack.length = 0;
  document.body.style.overflow = '';
}
