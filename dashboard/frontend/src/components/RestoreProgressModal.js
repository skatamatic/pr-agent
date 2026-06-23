import React, { useState, useEffect } from 'react';
import Modal from './Modal';

const RestoreProgressModal = ({ isOpen, onClose, filename, websocketService }) => {
  const [message, setMessage] = useState('Starting restore...');
  const [isCompleted, setIsCompleted] = useState(false);
  const [isError, setIsError] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    if (!websocketService || !isOpen) return;

    const handleProgressUpdate = (data) => {
      if (data.filename === filename) {
        setMessage(data.message);
      }
    };

    const handleRestoreComplete = (data) => {
      if (data.filename === filename) {
        setIsCompleted(true);
        
        if (data.success) {
          setMessage(data.message);
          setIsError(false);
          // Auto-close after 3 seconds on success
          setTimeout(() => {
            onClose();
            // Reset state for next use
            setMessage('Starting restore...');
            setIsCompleted(false);
            setIsError(false);
            setErrorMessage('');
          }, 3000);
        } else {
          setIsError(true);
          setErrorMessage(data.message);
          setMessage('Restore failed');
        }
      }
    };

    // Use websocket service event system
    websocketService.on('backup_restore_progress', handleProgressUpdate);
    websocketService.on('backup_restore_complete', handleRestoreComplete);

    return () => {
      websocketService.off('backup_restore_progress', handleProgressUpdate);
      websocketService.off('backup_restore_complete', handleRestoreComplete);
    };
  }, [websocketService, isOpen, onClose, filename]);

  const handleCloseModal = () => {
    if (isCompleted || isError) {
      onClose();
      // Reset state for next use
      setMessage('Starting restore...');
      setIsCompleted(false);
      setIsError(false);
      setErrorMessage('');
    }
  };

  if (!isOpen) return null;

  return (
    <Modal isOpen onClose={handleCloseModal} maxWidth="max-w-md" closeOnBackdrop={isCompleted || isError} ariaLabel="Restoring Database">
      <div className="p-6 text-center">
          <h3 className="text-lg font-semibold mb-4 text-gray-900 dark:text-white">
            {isCompleted ? (isError ? 'Restore Failed' : 'Restore Complete') : 'Restoring Database'}
          </h3>
          
          <div className="mb-4">
            <div className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              {filename}
            </div>
            
            <div className="text-sm text-gray-600 dark:text-gray-400">
              {message}
            </div>
            
            {isError && (
              <div className="mt-3 p-3 bg-red-100 dark:bg-red-900 border border-red-400 dark:border-red-600 rounded text-sm text-red-700 dark:text-red-300">
                {errorMessage}
              </div>
            )}
          </div>
          
          {isCompleted && (
            <div className="flex justify-center">
              <button
                onClick={handleCloseModal}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
              >
                Close
              </button>
            </div>
          )}
          
          {!isCompleted && (
            <div className="flex justify-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
          )}
      </div>
    </Modal>
  );
};

export default RestoreProgressModal; 