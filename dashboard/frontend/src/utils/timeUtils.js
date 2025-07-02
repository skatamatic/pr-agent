/**
 * Format time duration for display - shows minutes if < 1 hour, hours if >= 1 hour
 * @param {number} hours - Time in hours (can be fractional)
 * @param {boolean} includeUnit - Whether to include the unit (default: true)
 * @returns {string} Formatted time string
 */
export const formatDevTime = (hours, includeUnit = true) => {
  if (!hours && hours !== 0) return null;
  
  const absHours = Math.abs(hours);
  
  if (absHours < 1) {
    // Convert to minutes and round to nearest minute
    const minutes = Math.round(absHours * 60);
    if (minutes === 0) {
      return includeUnit ? '< 1min' : '< 1';
    }
    return includeUnit ? `${minutes}min` : minutes.toString();
  } else {
    // Show hours with 1 decimal place
    const formattedHours = absHours.toFixed(1);
    return includeUnit ? `${formattedHours}h` : formattedHours;
  }
};

/**
 * Format time duration with sign prefix for savings/waste indication
 * @param {number} hours - Time in hours (can be negative for waste)
 * @param {boolean} includeUnit - Whether to include the unit (default: true)
 * @returns {object} Object with formatted time and metadata
 */
export const formatTimeSaved = (hours, includeUnit = true) => {
  if (hours == null || hours === undefined) return null;
  
  const isNegative = hours < 0;
  const absHours = Math.abs(hours);
  const formattedTime = formatDevTime(absHours, includeUnit);
  
  if (isNegative) {
    return {
      value: absHours,
      type: 'wasted',
      display: `${formattedTime} wasted`,
      color: 'text-red-600 dark:text-red-400',
      icon: 'AlertTriangle',
      raw: formattedTime
    };
  } else {
    return {
      value: absHours,
      type: 'saved',
      display: `${formattedTime} saved`,
      color: 'text-green-600 dark:text-green-400',
      icon: 'TrendingUp',
      raw: formattedTime
    };
  }
};

/**
 * Format time duration for detailed insights display
 * @param {number} hours - Time in hours (can be fractional)
 * @returns {string} Formatted time string with proper precision
 */
export const formatInsightsTime = (hours) => {
  if (!hours && hours !== 0) return '0.00 hours';
  
  const absHours = Math.abs(hours);
  
  if (absHours < 1) {
    // Convert to minutes and show with proper precision
    const minutes = absHours * 60;
    if (minutes < 1) {
      return '< 1 minute';
    } else if (minutes < 60) {
      return `${Math.round(minutes)} minute${Math.round(minutes) !== 1 ? 's' : ''}`;
    }
  }
  
  // For hours >= 1, show with 2 decimal places as before
  return `${absHours.toFixed(2)} hour${absHours !== 1 ? 's' : ''}`;
};

/**
 * Format time duration for compact display (no unit, just number)
 * @param {number} hours - Time in hours (can be fractional)
 * @returns {string} Formatted time string without unit
 */
export const formatCompactTime = (hours) => {
  const formatted = formatDevTime(hours, false);
  return formatted || '0';
};

/**
 * Ensure a timestamp is properly converted to a Date object
 * Handles various input formats and ensures UTC timestamps are correctly interpreted
 * @param {string|Date} timestamp - The timestamp to convert
 * @returns {Date|null} Properly converted Date object or null if invalid
 */
export const parseTimestamp = (timestamp) => {
  if (!timestamp) return null;
  
  try {
    // If it's already a Date object, return it
    if (timestamp instanceof Date) {
      return isNaN(timestamp.getTime()) ? null : timestamp;
    }
    
    // If it's a string, parse it
    if (typeof timestamp === 'string') {
      const date = new Date(timestamp);
      return isNaN(date.getTime()) ? null : date;
    }
    
    return null;
  } catch (error) {
    console.warn('Failed to parse timestamp:', timestamp, error);
    return null;
  }
};

/**
 * Format a timestamp for display in the user's local timezone
 * @param {string|Date} timestamp - The UTC timestamp to format
 * @param {Object} options - Formatting options
 * @returns {string} Formatted timestamp string
 */
export const formatTimestamp = (timestamp, options = {}) => {
  const date = parseTimestamp(timestamp);
  if (!date) return 'Invalid date';
  
  const defaultOptions = {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    ...options
  };
  
  try {
    return date.toLocaleString(undefined, defaultOptions);
  } catch (error) {
    console.warn('Failed to format timestamp:', timestamp, error);
    return date.toString();
  }
};

/**
 * Format a timestamp for compact display (no seconds)
 * @param {string|Date} timestamp - The UTC timestamp to format
 * @returns {string} Formatted timestamp string
 */
export const formatCompactTimestamp = (timestamp) => {
  return formatTimestamp(timestamp, { second: undefined });
};

/**
 * Format a timestamp for relative display (e.g., "2 hours ago")
 * @param {string|Date} timestamp - The UTC timestamp to format
 * @returns {string} Relative time string
 */
export const formatRelativeTime = (timestamp) => {
  const date = parseTimestamp(timestamp);
  if (!date) return 'Unknown time';
  
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);
  
  if (diffSec < 60) {
    return 'Just now';
  } else if (diffMin < 60) {
    return `${diffMin} minute${diffMin !== 1 ? 's' : ''} ago`;
  } else if (diffHour < 24) {
    return `${diffHour} hour${diffHour !== 1 ? 's' : ''} ago`;
  } else if (diffDay < 7) {
    return `${diffDay} day${diffDay !== 1 ? 's' : ''} ago`;
  } else {
    return formatCompactTimestamp(timestamp);
  }
};

/**
 * Get current UTC timestamp as ISO string
 * @returns {string} Current UTC timestamp
 */
export const getCurrentUTCTimestamp = () => {
  return new Date().toISOString();
};

/**
 * Validate if a timestamp is properly in UTC format
 * @param {string} timestamp - Timestamp string to validate
 * @returns {boolean} True if timestamp appears to be UTC
 */
export const isUTCTimestamp = (timestamp) => {
  if (!timestamp || typeof timestamp !== 'string') return false;
  
  // Check if it ends with 'Z' (UTC indicator) or has timezone offset
  return timestamp.endsWith('Z') || 
         /\+\d{2}:\d{2}$/.test(timestamp) || 
         /-\d{2}:\d{2}$/.test(timestamp);
}; 