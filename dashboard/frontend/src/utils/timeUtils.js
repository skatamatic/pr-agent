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
      icon: '⚠️',
      raw: formattedTime
    };
  } else {
    return {
      value: absHours,
      type: 'saved',
      display: `${formattedTime} saved`,
      color: 'text-green-600 dark:text-green-400',
      icon: '📈',
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