import React, { createContext, useContext, useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { acquireModalLock, isTopModal, releaseModalLock } from '../utils/modalStack';

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

const ModalTitleContext = createContext(null);

/**
 * Full-viewport modal rendered via portal (avoids fixed-position gaps from nested transforms).
 */
const Modal = ({
  open,
  isOpen,
  onClose,
  children,
  maxWidth = 'max-w-2xl',
  zIndex = 'z-[9999]',
  closeOnBackdrop = true,
  panelClassName = '',
  ariaLabel,
}) => {
  const visible = open ?? isOpen;
  const modalId = useId();
  const titleId = useId();
  const panelRef = useRef(null);
  const previousFocusRef = useRef(null);

  useEffect(() => {
    if (!visible) return undefined;
    acquireModalLock(modalId);
    return () => releaseModalLock(modalId);
  }, [visible, modalId]);

  useEffect(() => {
    if (!visible || !onClose) return undefined;
    const onKeyDown = (event) => {
      if (event.key !== 'Escape') return;
      if (!isTopModal(modalId)) return;
      event.preventDefault();
      event.stopPropagation();
      onClose();
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [visible, onClose, modalId]);

  useEffect(() => {
    if (!visible) return undefined;

    previousFocusRef.current = document.activeElement;
    const panel = panelRef.current;
    if (!panel) return undefined;

    const focusTarget = panel.querySelector(FOCUSABLE_SELECTOR) || panel;
    if (focusTarget === panel) {
      panel.tabIndex = -1;
    }
    focusTarget.focus();

    const onKeyDown = (event) => {
      if (event.key !== 'Tab' || !panelRef.current) return;

      const focusables = Array.from(panelRef.current.querySelectorAll(FOCUSABLE_SELECTOR))
        .filter((el) => el.offsetParent !== null || el === document.activeElement);

      if (focusables.length === 0) {
        event.preventDefault();
        panelRef.current.focus();
        return;
      }

      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;

      if (event.shiftKey) {
        if (active === first || !panelRef.current.contains(active)) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      const previous = previousFocusRef.current;
      if (previous && typeof previous.focus === 'function') {
        previous.focus();
      }
    };
  }, [visible]);

  if (!visible) return null;

  return createPortal(
    <div
      className={`modal-root ${zIndex}`}
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel}
      aria-labelledby={ariaLabel ? undefined : titleId}
    >
      <div
        className="modal-backdrop"
        onClick={closeOnBackdrop && onClose ? onClose : undefined}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        className={`modal-panel ${maxWidth} ${panelClassName}`.trim()}
      >
        <ModalTitleContext.Provider value={titleId}>
          {children}
        </ModalTitleContext.Provider>
      </div>
    </div>,
    document.body
  );
};

const ModalHeader = ({ title, subtitle, children, className = '' }) => {
  const titleId = useContext(ModalTitleContext);

  return (
    <div className={`modal-header ${className}`.trim()}>
      {children ?? (
        <>
          {title && (
            <h3 id={titleId || undefined} className="modal-title">
              {title}
            </h3>
          )}
          {subtitle && <p className="modal-subtitle">{subtitle}</p>}
        </>
      )}
    </div>
  );
};

const ModalBody = ({ children, className = '' }) => (
  <div className={`modal-body ${className}`.trim()}>{children}</div>
);

const ModalFooter = ({ children, className = '' }) => (
  <div className={`modal-footer ${className}`.trim()}>{children}</div>
);

Modal.Header = ModalHeader;
Modal.Body = ModalBody;
Modal.Footer = ModalFooter;

export default Modal;
