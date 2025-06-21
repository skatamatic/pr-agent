import React from 'react';
import { useToast } from '../contexts/ToastContext';

const ToastDemo = () => {
  const { showSuccess, showError, showProgress, updateToast } = useToast();

  const handleShowProgress = () => {
    const toastId = showProgress(
      'Review in Progress',
      'Analyzing PR #123 for user/repo',
      {
        details: ['Fetching context...', 'Running analysis...', 'Generating suggestions...']
      }
    );

    // Simulate progress updates
    setTimeout(() => {
      updateToast(toastId, {
        title: 'Review in Progress',
        message: 'Analyzing PR #123 for user/repo',
        details: ['✅ Fetching context...', 'Running analysis...', 'Generating suggestions...']
      });
    }, 2000);

    setTimeout(() => {
      updateToast(toastId, {
        title: 'Review in Progress', 
        message: 'Analyzing PR #123 for user/repo',
        details: ['✅ Fetching context...', '✅ Running analysis...', 'Generating suggestions...']
      });
    }, 4000);

    setTimeout(() => {
      updateToast(toastId, {
        type: 'success',
        title: 'Review Completed',
        message: 'Successfully analyzed PR #123',
        details: ['✅ Fetching context...', '✅ Running analysis...', '✅ Generating suggestions...'],
        dismissible: true,
        autoDismiss: true
      });
    }, 6000);
  };

  const handleShowSuccess = () => {
    showSuccess(
      'Review Completed',
      'Successfully analyzed PR #456 with 3 suggestions',
      {
        details: ['Found 2 code improvements', 'Suggested 1 test addition', 'No security issues detected']
      }
    );
  };

  const handleShowError = () => {
    showError(
      'Review Failed',
      'Failed to analyze PR #789 due to API timeout',
      {
        details: ['Connection timeout after 30s', 'Retry the operation', 'Check network connectivity']
      }
    );
  };

  return (
    <div className="p-4 space-y-4 bg-white dark:bg-gray-800 rounded-lg shadow">
      <h3 className="text-lg font-medium text-gray-900 dark:text-white">Toast Demo</h3>
      <div className="space-x-4">
        <button
          onClick={handleShowProgress}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
        >
          Show Progress Toast
        </button>
        <button
          onClick={handleShowSuccess}
          className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
        >
          Show Success Toast
        </button>
        <button
          onClick={handleShowError}
          className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
        >
          Show Error Toast
        </button>
      </div>
    </div>
  );
};

export default ToastDemo; 