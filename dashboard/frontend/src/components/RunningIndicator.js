import React from 'react';

const RunningIndicator = ({ size = 'sm', className = '', variant = 'spinner' }) => {
  const sizeClasses = {
    xs: 'w-3 h-3',
    sm: 'w-4 h-4',
    md: 'w-5 h-5',
    lg: 'w-6 h-6',
    xl: 'w-8 h-8'
  };

  const strokeWidths = {
    xs: '2',
    sm: '2',
    md: '2.5',
    lg: '3',
    xl: '3'
  };

  const svgSize = {
    xs: 12,
    sm: 16,
    md: 20,
    lg: 24,
    xl: 32
  };

  const currentSize = svgSize[size];
  const strokeWidth = strokeWidths[size];
  const radius = (currentSize - parseFloat(strokeWidth)) / 2;
  const circumference = 2 * Math.PI * radius;

  // Spinner variant (default)
  if (variant === 'spinner') {
    return (
      <div className={`${sizeClasses[size]} ${className} flex items-center justify-center`}>
        <svg
          className="animate-spin"
          width={currentSize}
          height={currentSize}
          viewBox={`0 0 ${currentSize} ${currentSize}`}
          style={{ animationDuration: '1s' }}
        >
          {/* Background circle */}
          <circle
            cx={currentSize / 2}
            cy={currentSize / 2}
            r={radius}
            stroke="currentColor"
            strokeWidth={strokeWidth}
            fill="none"
            className="text-gray-200 dark:text-gray-700"
          />
          {/* Animated progress circle */}
          <circle
            cx={currentSize / 2}
            cy={currentSize / 2}
            r={radius}
            stroke="currentColor"
            strokeWidth={strokeWidth}
            fill="none"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * 0.75}
            className="text-blue-500 dark:text-blue-400"
            style={{
              transformOrigin: 'center',
              transition: 'stroke-dashoffset 0.3s ease'
            }}
          />
        </svg>
      </div>
    );
  }

  // Pulse variant - smooth pulsing circle
  if (variant === 'pulse') {
    return (
      <div className={`${sizeClasses[size]} ${className} flex items-center justify-center`}>
        <div className="relative">
          <div className="absolute inset-0 bg-blue-500 dark:bg-blue-400 rounded-full animate-ping opacity-20"></div>
          <div className="relative bg-blue-500 dark:bg-blue-400 rounded-full animate-pulse"></div>
        </div>
      </div>
    );
  }

  // Default fallback
  return (
    <div className={`${sizeClasses[size]} ${className} flex items-center justify-center`}>
      <svg
        className="animate-spin"
        width={currentSize}
        height={currentSize}
        viewBox={`0 0 ${currentSize} ${currentSize}`}
        style={{ animationDuration: '1s' }}
      >
        <circle
          cx={currentSize / 2}
          cy={currentSize / 2}
          r={radius}
          stroke="currentColor"
          strokeWidth={strokeWidth}
          fill="none"
          className="text-gray-200 dark:text-gray-700"
        />
        <circle
          cx={currentSize / 2}
          cy={currentSize / 2}
          r={radius}
          stroke="currentColor"
          strokeWidth={strokeWidth}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * 0.75}
          className="text-blue-500 dark:text-blue-400"
          style={{
            transformOrigin: 'center',
            transition: 'stroke-dashoffset 0.3s ease'
          }}
        />
      </svg>
    </div>
  );
};

export default RunningIndicator; 