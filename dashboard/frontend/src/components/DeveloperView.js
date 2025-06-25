import React, { useState, useContext } from 'react';
import { Play, Database, AlertTriangle, Trash2, Activity, Code, Zap, CheckCircle, XCircle } from 'lucide-react';
import apiService from '../services/api';
import { ToastContext } from '../contexts/ToastContext';
import ViewHeader from './ViewHeader';

const DeveloperView = ({ onRefresh }) => {
  const [loading, setLoading] = useState({});
  const [currentOperationId, setCurrentOperationId] = useState(null);
  const { showSuccess, showError, showProgress } = useContext(ToastContext);

  const handleButtonClick = async (action, buttonKey) => {
    setLoading(prev => ({ ...prev, [buttonKey]: true }));
    
    try {
      let result;
      let title, message;
      
      switch (action) {
        case 'generateTestData':
          result = await apiService.generateTestData();
          title = 'Test Data Generated';
          message = `Created ${result.data.operations} operations and ${result.data.logs} logs`;
          break;
        case 'simulateActivity':
          result = await apiService.simulateActivity();
          title = 'Activity Simulation';
          message = 'Live activity simulation started';
          // Store the operation ID for fail/succeed actions
          if (result.data?.operation_id) {
            setCurrentOperationId(result.data.operation_id);
          }
          // Show progress toast for simulation
          showProgress('Simulating Live Activity', 'Processing mock operations and updates...');
          break;
        case 'failActivity':
          if (!currentOperationId) {
            throw new Error('No active operation to fail');
          }
          result = await apiService.failActivity(currentOperationId);
          title = 'Activity Failed';
          message = `Operation ${currentOperationId} marked as failed`;
          setCurrentOperationId(null); // Clear the operation ID
          break;
        case 'succeedActivity':
          if (!currentOperationId) {
            throw new Error('No active operation to succeed');
          }
          result = await apiService.succeedActivity(currentOperationId);
          title = 'Activity Succeeded';
          message = `Operation ${currentOperationId} marked as completed`;
          setCurrentOperationId(null); // Clear the operation ID
          break;
        case 'triggerError':
          result = await apiService.triggerError();
          // This should actually trigger an error, not success
          showError('Test Error Triggered', result.message || 'This is a test error to verify error handling');
          return; // Exit early to avoid showing success
        case 'clearData':
          result = await apiService.clearData();
          title = 'Data Cleared';
          message = 'All operations and logs removed from database';
          break;
        case 'refreshJobCounts':
          result = await apiService.refreshJobCounts();
          title = 'Job Counts Refreshed';
          message = result.message || `Updated ${result.data?.updated_jobs || 0} jobs`;
          break;
        default:
          throw new Error('Unknown action');
      }
      
      showSuccess(title, result.message || message);
      
      // Trigger data refresh after successful operations
      if (onRefresh && ['generateTestData', 'simulateActivity', 'failActivity', 'succeedActivity', 'triggerError', 'clearData', 'refreshJobCounts'].includes(action)) {
        setTimeout(() => {
          onRefresh();
        }, 1000); // Give backend time to process
      }
      
    } catch (error) {
      console.error(`Failed to ${action}:`, error);
      const actionName = action.replace(/([A-Z])/g, ' $1').toLowerCase();
      showError(`${actionName.charAt(0).toUpperCase() + actionName.slice(1)} Failed`, error.message || 'An unexpected error occurred');
    } finally {
      setLoading(prev => ({ ...prev, [buttonKey]: false }));
    }
  };

  const developerButtons = [
    {
      key: 'generateTestData',
      label: 'Generate Test Data',
      description: 'Create sample operations and logs for testing',
      icon: Database,
      color: 'blue',
      action: () => handleButtonClick('generateTestData', 'generateTestData')
    },
    {
      key: 'simulateActivity',
      label: currentOperationId ? 'Live Activity Running' : 'Start Live Activity',
      description: currentOperationId ? 'An operation is currently being simulated' : 'Begin a mock operation with real-time updates',
      icon: Activity,
      color: currentOperationId ? 'gray' : 'green',
      action: () => handleButtonClick('simulateActivity', 'simulateActivity'),
      disabled: currentOperationId !== null
    },
    {
      key: 'failActivity',
      label: 'Fail Current Activity',
      description: 'Mark the current live activity as failed',
      icon: XCircle,
      color: 'red',
      action: () => handleButtonClick('failActivity', 'failActivity'),
      disabled: currentOperationId === null
    },
    {
      key: 'succeedActivity',
      label: 'Complete Current Activity',
      description: 'Mark the current live activity as completed successfully',
      icon: CheckCircle,
      color: 'green',
      action: () => handleButtonClick('succeedActivity', 'succeedActivity'),
      disabled: currentOperationId === null
    },
    {
      key: 'testSuccess',
      label: 'Test Success Toast',
      description: 'Test success notification system',
      icon: CheckCircle,
      color: 'green',
      action: () => showSuccess('Test Success', 'This is a test success message to verify the notification system')
    },
    {
      key: 'triggerError',
      label: 'Test Error Toast',
      description: 'Test error notification system',
      icon: AlertTriangle,
      color: 'orange',
      action: () => showError('Test Error', 'This is a test error message to verify the notification system')
    },
    {
      key: 'refreshJobCounts',
      label: 'Refresh Job Counts',
      description: 'Recalculate operations and logs counts for all jobs',
      icon: Zap,
      color: 'blue',
      action: () => handleButtonClick('refreshJobCounts', 'refreshJobCounts')
    },
    {
      key: 'clearData',
      label: 'Clear All Data',
      description: 'Remove all operations and logs from database',
      icon: Trash2,
      color: 'red',
      action: () => handleButtonClick('clearData', 'clearData')
    }
  ];

  const getButtonStyles = (color, isLoading, isDisabled) => {
    const baseStyles = "group relative overflow-hidden rounded-xl p-6 transition-all duration-300 transform hover:scale-105 hover:shadow-xl";
    const disabledStyles = (isLoading || isDisabled) ? "opacity-50 cursor-not-allowed" : "cursor-pointer";
    
    const colorStyles = {
      blue: "bg-gradient-to-br from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700",
      green: "bg-gradient-to-br from-green-500 to-green-600 hover:from-green-600 hover:to-green-700",
      orange: "bg-gradient-to-br from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700",
      red: "bg-gradient-to-br from-red-500 to-red-600 hover:from-red-600 hover:to-red-700",
      gray: "bg-gradient-to-br from-gray-500 to-gray-600 hover:from-gray-600 hover:to-gray-700"
    };
    
    return `${baseStyles} ${colorStyles[color]} ${disabledStyles}`;
  };

  const getIconStyles = (isLoading) => {
    return `h-8 w-8 text-white transition-transform duration-300 ${isLoading ? 'animate-spin' : 'group-hover:scale-110'}`;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <ViewHeader 
        title="Developer Tools"
        subtitle="Testing utilities and debugging tools for development"
        icon={Code}
      />
      
      {/* Warning Banner */}
      <div className="bg-gradient-to-r from-yellow-50 to-orange-50 dark:from-yellow-900/20 dark:to-orange-900/20 border border-yellow-200 dark:border-yellow-800 rounded-xl p-4">
        <div className="flex items-center">
          <AlertTriangle className="h-5 w-5 text-yellow-600 dark:text-yellow-400 mr-2" />
          <div>
            <p className="text-sm font-semibold text-yellow-800 dark:text-yellow-200">Developer Mode Active</p>
            <p className="text-xs text-yellow-700 dark:text-yellow-300 mt-1">
              These tools are for development and testing only. Use with caution in production environments.
            </p>
          </div>
        </div>
      </div>

      {/* Active Operation Banner */}
      {currentOperationId && (
        <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border border-blue-200 dark:border-blue-800 rounded-xl p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <Activity className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-2 animate-pulse" />
              <div>
                <p className="text-sm font-semibold text-blue-800 dark:text-blue-200">Live Activity Running</p>
                <p className="text-xs text-blue-700 dark:text-blue-300 mt-1">
                  Operation ID: {currentOperationId}
                </p>
              </div>
            </div>
            <div className="flex space-x-2">
              <span className="text-xs text-blue-600 dark:text-blue-400">Use Fail/Succeed buttons to complete</span>
            </div>
          </div>
        </div>
      )}

      {/* Developer Buttons Grid */}
      <div className="space-y-6">
        {/* Special layout for fail/succeed buttons when active */}
        {currentOperationId && (
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
              <Activity className="h-5 w-5 mr-2 text-blue-600 dark:text-blue-400 animate-pulse" />
              Active Operation Controls
            </h3>
            <div className="grid grid-cols-2 gap-4">
              {developerButtons.filter(button => ['failActivity', 'succeedActivity'].includes(button.key)).map((button) => {
                const Icon = button.icon;
                const isLoading = loading[button.key];
                const isDisabled = button.disabled || false;
                
                return (
                  <div
                    key={button.key}
                    className={getButtonStyles(button.color, isLoading, isDisabled)}
                    onClick={(isLoading || isDisabled) ? undefined : button.action}
                  >
                    {/* Background Pattern */}
                    <div className="absolute inset-0 bg-white/10 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                    
                    {/* Content */}
                    <div className="relative z-10">
                      <div className="flex items-center justify-between mb-4">
                        <Icon className={getIconStyles(isLoading)} />
                        {isLoading && (
                          <div className="flex items-center text-white/80 text-sm">
                            <Zap className="h-4 w-4 mr-1 animate-pulse" />
                            Processing...
                          </div>
                        )}
                      </div>
                      
                      <h3 className="text-xl font-bold text-white mb-2">{button.label}</h3>
                      <p className="text-white/80 text-sm leading-relaxed">{button.description}</p>
                      
                      {/* Hover Effect */}
                      <div className="absolute bottom-0 left-0 right-0 h-1 bg-white/20 transform scale-x-0 group-hover:scale-x-100 transition-transform duration-300" />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
        
        {/* Regular buttons grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {developerButtons.filter(button => !['failActivity', 'succeedActivity'].includes(button.key)).map((button) => {
            const Icon = button.icon;
            const isLoading = loading[button.key];
            const isDisabled = button.disabled || false;
            
            return (
              <div
                key={button.key}
                className={getButtonStyles(button.color, isLoading, isDisabled)}
                onClick={(isLoading || isDisabled) ? undefined : button.action}
              >
              {/* Background Pattern */}
              <div className="absolute inset-0 bg-white/10 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
              
              {/* Content */}
              <div className="relative z-10">
                <div className="flex items-center justify-between mb-4">
                  <Icon className={getIconStyles(isLoading)} />
                  {isLoading && (
                    <div className="flex items-center text-white/80 text-sm">
                      <Zap className="h-4 w-4 mr-1 animate-pulse" />
                      Processing...
                    </div>
                  )}
                </div>
                
                <h3 className="text-xl font-bold text-white mb-2">{button.label}</h3>
                <p className="text-white/80 text-sm leading-relaxed">{button.description}</p>
                
                {/* Hover Effect */}
                <div className="absolute bottom-0 left-0 right-0 h-1 bg-white/20 transform scale-x-0 group-hover:scale-x-100 transition-transform duration-300" />
              </div>
            </div>
          );
        })}
      </div>

      {/* Additional Info */}
      <div className="bg-gradient-to-br from-gray-50 to-white dark:from-gray-800 dark:to-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
          <Play className="h-5 w-5 mr-2 text-blue-600 dark:text-blue-400" />
          Quick Actions Guide
        </h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div className="space-y-2">
            <h4 className="font-semibold text-gray-700 dark:text-gray-300">Testing Workflow:</h4>
            <ol className="list-decimal list-inside space-y-1 text-gray-600 dark:text-gray-400">
              <li>Generate test data to populate dashboard</li>
              <li>Simulate live activity to test real-time updates</li>
              <li>Trigger errors to test error handling</li>
              <li>Clear data when testing is complete</li>
            </ol>
          </div>
          
          <div className="space-y-2">
            <h4 className="font-semibold text-gray-700 dark:text-gray-300">Real-time Features:</h4>
            <ul className="list-disc list-inside space-y-1 text-gray-600 dark:text-gray-400">
              <li>WebSocket connections for live updates</li>
              <li>Toast notifications for user feedback</li>
              <li>Status tracking and progress indicators</li>
              <li>Error handling and recovery</li>
            </ul>
          </div>
        </div>
      </div>
      </div>
    </div>
  );
};

export default DeveloperView; 