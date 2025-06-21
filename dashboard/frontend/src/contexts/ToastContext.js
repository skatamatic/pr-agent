import React, { createContext, useContext, useState, useCallback, useRef } from 'react';
import { CheckCircle, AlertCircle, Activity, X } from 'lucide-react';

const ToastContext = createContext();

export const useToast = () => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};

const ToastItem = ({ toast, onDismiss }) => {
  const getToastStyles = () => {
    switch (toast.type) {
      case 'success':
        return 'bg-green-50 border-green-200 text-green-800 dark:bg-green-900/50 dark:border-green-700 dark:text-green-100';
      case 'error':
        return 'bg-red-50 border-red-200 text-red-800 dark:bg-red-900/50 dark:border-red-700 dark:text-red-100';
      case 'progress':
        return 'bg-blue-50 border-blue-200 text-blue-800 dark:bg-blue-900/50 dark:border-blue-700 dark:text-blue-100';
      default:
        return 'bg-gray-50 border-gray-200 text-gray-800 dark:bg-gray-900/50 dark:border-gray-600 dark:text-gray-100';
    }
  };

  const getIcon = () => {
    switch (toast.type) {
      case 'success':
        return <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />;
      case 'error':
        return <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400" />;
      case 'progress':
        return <Activity className="h-5 w-5 text-blue-600 dark:text-blue-400 animate-spin" />;
      default:
        return <AlertCircle className="h-5 w-5 text-gray-600 dark:text-gray-400" />;
    }
  };

  const formatTime = (timestamp) => {
    return new Date(timestamp).toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  return (
    <div className={`rounded-lg border p-4 shadow-lg backdrop-blur-sm transition-all duration-300 ${getToastStyles()}`}>
      <div className="flex items-start space-x-3">
        <div className="flex-shrink-0">
          {getIcon()}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium">{toast.title}</h4>
            <span className="text-xs opacity-60 ml-2 flex-shrink-0">
              {formatTime(toast.timestamp)}
            </span>
          </div>
          {toast.message && (
            <p className="mt-1 text-sm opacity-90">{toast.message}</p>
          )}
          {toast.details && (
            <div className="mt-2 text-xs opacity-75">
              {Array.isArray(toast.details) ? (
                <ul className="list-disc list-inside space-y-1">
                  {toast.details.map((detail, index) => (
                    <li key={index}>{detail}</li>
                  ))}
                </ul>
              ) : (
                <p>{toast.details}</p>
              )}
            </div>
          )}
        </div>
        {toast.dismissible && (
          <button
            onClick={() => onDismiss(toast.id)}
            className="flex-shrink-0 rounded-md p-1 hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
};

export const ToastProvider = ({ children }) => {
  const [toasts, setToasts] = useState([]);
  const toastIdRef = useRef(0);
  const errorStateRef = useRef({}); // Track error states to prevent spam

  const generateId = () => {
    toastIdRef.current += 1;
    return toastIdRef.current;
  };

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(toast => toast.id !== id));
  }, []);

  const showToast = useCallback((messageOrConfig, type = 'info', autoDismiss = true, errorKey = null) => {
    // Handle both string messages and config objects
    let title, message, details;
    
    if (typeof messageOrConfig === 'string') {
      // Legacy string format - split on first colon if present
      const colonIndex = messageOrConfig.indexOf(':');
      if (colonIndex > 0 && colonIndex < 50) { // Only split if colon is reasonably early
        title = messageOrConfig.substring(0, colonIndex).trim();
        message = messageOrConfig.substring(colonIndex + 1).trim();
      } else {
        title = messageOrConfig;
      }
    } else {
      // Config object format
      title = messageOrConfig.title;
      message = messageOrConfig.message;
      details = messageOrConfig.details;
    }

    // Handle error state tracking to prevent spam
    if (type === 'error' && errorKey) {
      // Check if this error is already being shown
      if (errorStateRef.current[errorKey]) {
        return; // Don't show duplicate error
      }
      // Mark this error as active
      errorStateRef.current[errorKey] = true;
    }

    // Handle success after error (falling edge)
    if (type === 'success' && errorKey && errorStateRef.current[errorKey]) {
      // Clear the error state
      errorStateRef.current[errorKey] = false;
      // Show "functionality restored" message instead
      if (!title.includes('restored') && !title.includes('Restored')) {
        title = title.includes('connectivity') ? title : `${title} - Functionality restored`;
      }
    }

    const id = generateId();
    const newToast = {
      id,
      title,
      message,
      details,
      type,
      autoDismiss,
      dismissible: type !== 'progress', // Progress toasts are not dismissible
      errorKey,
      timestamp: Date.now()
    };

    setToasts(prev => {
      let updatedToasts = [...prev];
      
      // For progress toasts, remove any existing progress toasts first
      if (type === 'progress') {
        updatedToasts = updatedToasts.filter(toast => toast.type !== 'progress');
      }
      
      // For error toasts with the same errorKey, replace the existing one
      if (type === 'error' && errorKey) {
        updatedToasts = updatedToasts.filter(toast => !(toast.type === 'error' && toast.errorKey === errorKey));
      }
      
      // Add the new toast
      updatedToasts.push(newToast);
      
      // Implement max 6 toasts limit with smart removal - but never remove progress toasts
      const regularToasts = updatedToasts.filter(toast => toast.type !== 'progress');
      const progressToasts = updatedToasts.filter(toast => toast.type === 'progress');
      
      if (regularToasts.length > 6) {
        // Separate error toasts from other regular toasts
        const errorToasts = regularToasts.filter(toast => toast.type === 'error' || !toast.autoDismiss);
        const otherRegularToasts = regularToasts.filter(toast => toast.type !== 'error' && toast.autoDismiss);
        
        // Remove oldest other regular toasts first, then oldest error toasts if needed
        const toastsToKeep = 6;
        if (errorToasts.length >= toastsToKeep) {
          // Keep only the newest error toasts
          updatedToasts = [...progressToasts, ...errorToasts.slice(-toastsToKeep)];
        } else {
          // Keep all error toasts and fill remaining slots with newest other regular toasts
          const otherSlotsAvailable = toastsToKeep - errorToasts.length;
          const otherToastsToKeep = otherRegularToasts.slice(-otherSlotsAvailable);
          updatedToasts = [...progressToasts, ...errorToasts, ...otherToastsToKeep];
        }
      }
      
      // Sort regular toasts: success/info toasts first (by timestamp), then error toasts (by timestamp)
      // Progress toasts are kept separate and don't participate in sorting
      const finalProgressToasts = updatedToasts.filter(toast => toast.type === 'progress');
      const finalRegularToasts = updatedToasts.filter(toast => toast.type !== 'progress');
      
      const successInfoToasts = finalRegularToasts.filter(toast => 
        toast.type === 'success' || (toast.type !== 'error' && toast.autoDismiss)
      ).sort((a, b) => a.timestamp - b.timestamp);
      
      const errorToasts = finalRegularToasts.filter(toast => 
        toast.type === 'error' || !toast.autoDismiss
      ).sort((a, b) => a.timestamp - b.timestamp);
      
      return [...finalProgressToasts, ...successInfoToasts, ...errorToasts];
    });

    // Auto-dismiss logic
    if (autoDismiss && type !== 'progress') {
      const dismissTime = type === 'error' ? 0 : 10000; // Errors don't auto-dismiss, others dismiss after 10s
      if (dismissTime > 0) {
        setTimeout(() => {
          removeToast(id);
        }, dismissTime);
      }
    }

    return id;
  }, [removeToast]);

  // Smart error handling functions
  const handleApiError = useCallback((error, context = 'operation') => {
    const errorKey = `api_${context}`;
    const message = error.message || 'An unexpected error occurred';
    showToast(`${context.charAt(0).toUpperCase() + context.slice(1)} failed: ${message}`, 'error', false, errorKey);
  }, [showToast]);

  const handleApiSuccess = useCallback((message, context = 'operation') => {
    const errorKey = `api_${context}`;
    showToast(message, 'success', true, errorKey);
  }, [showToast]);

  const handleSystemError = useCallback((error, systemComponent) => {
    const errorKey = `system_${systemComponent}`;
    // Standardize component names for consistent casing
    const componentName = systemComponent.toLowerCase().replace(/\b\w/g, l => l.toUpperCase());
    const message = `${componentName} error: ${error.message || 'Service unavailable'}`;
    showToast(message, 'error', false, errorKey);
  }, [showToast]);

  const handleSystemRestore = useCallback((systemComponent) => {
    const errorKey = `system_${systemComponent}`;
    // Standardize component names for consistent casing
    const componentName = systemComponent.toLowerCase().replace(/\b\w/g, l => l.toUpperCase());
    const message = `${componentName} connectivity restored`;
    showToast(message, 'success', true, errorKey);
  }, [showToast]);

  const clearErrorState = useCallback((errorKey) => {
    if (errorStateRef.current[errorKey]) {
      errorStateRef.current[errorKey] = false;
      // Remove any existing error toasts with this key
      setToasts(prev => prev.filter(toast => !(toast.type === 'error' && toast.errorKey === errorKey)));
    }
  }, []);

  const clearAllToasts = useCallback(() => {
    setToasts([]);
    errorStateRef.current = {};
  }, []);

  // Helper function to get toast statistics (for debugging)
  const getToastStats = useCallback(() => {
    const stats = {
      total: toasts.length,
      byType: {},
      statusToasts: 0,
      regularToasts: 0
    };
    
    toasts.forEach(toast => {
      stats.byType[toast.type] = (stats.byType[toast.type] || 0) + 1;
      if (toast.type === 'error' || toast.type === 'progress' || !toast.autoDismiss) {
        stats.statusToasts++;
      } else {
        stats.regularToasts++;
      }
    });
    
    return stats;
  }, [toasts]);

  // Convenience functions for common toast types
  const showSuccess = useCallback((title, message = '', options = {}) => {
    return showToast({
      title,
      message,
      details: options.details
    }, 'success', options.autoDismiss !== false, options.errorKey);
  }, [showToast]);

  const showError = useCallback((title, message = '', options = {}) => {
    return showToast({
      title,
      message,
      details: options.details
    }, 'error', options.autoDismiss === true, options.errorKey);
  }, [showToast]);

  const showProgress = useCallback((title, message = '', options = {}) => {
    return showToast({
      title,
      message,
      details: options.details
    }, 'progress', false, options.errorKey);
  }, [showToast]);

  const updateToast = useCallback((id, updates) => {
    setToasts(prev => prev.map(toast => 
      toast.id === id 
        ? { ...toast, ...updates, timestamp: Date.now() }
        : toast
    ));
  }, []);

  const value = {
    toasts,
    showToast,
    showSuccess,
    showError,
    showProgress,
    updateToast,
    removeToast,
    handleApiError,
    handleApiSuccess,
    handleSystemError,
    handleSystemRestore,
    clearErrorState,
    clearAllToasts,
    getToastStats
  };

  return (
    <ToastContext.Provider value={value}>
      {children}
      
      {/* Live Activity Toast Container - Bottom Left */}
      <div className="fixed bottom-4 left-4 z-50 space-y-3 max-w-xs w-full">
        {toasts.filter(toast => toast.type === 'progress').map(toast => (
          <ToastItem
            key={toast.id}
            toast={toast}
            onDismiss={removeToast}
          />
        ))}
      </div>
      
      {/* Regular Toast Container - Bottom Right */}
      <div className="fixed bottom-4 right-4 z-50 space-y-3 max-w-xs w-full">
        {toasts.filter(toast => toast.type !== 'progress').length >= 6 && (
          <div className="text-xs text-gray-500 dark:text-gray-400 text-center p-2 bg-gray-100 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
            Toast limit reached (6/6) - Older toasts auto-removed
          </div>
        )}
        {toasts.filter(toast => toast.type !== 'progress').map(toast => (
          <ToastItem
            key={toast.id}
            toast={toast}
            onDismiss={removeToast}
          />
        ))}
      </div>
    </ToastContext.Provider>
  );
};

export { ToastContext }; 