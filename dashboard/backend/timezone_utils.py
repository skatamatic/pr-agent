"""
Timezone utility functions for consistent datetime handling across the dashboard.
Prevents offset-naive vs offset-aware datetime comparison errors.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Union
import logging

logger = logging.getLogger(__name__)

def utcnow_aware() -> datetime:
    """
    Get current UTC time as timezone-aware datetime.
    
    Returns:
        datetime: Current UTC time with timezone info
    """
    return datetime.now(timezone.utc)

def ensure_timezone_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Convert naive datetime to timezone-aware (assuming UTC) or return already aware datetime.
    
    Args:
        dt: Datetime to convert (can be None, naive, or already aware)
        
    Returns:
        datetime: Timezone-aware datetime or None if input was None
    """
    if dt is None:
        return None
    
    if dt.tzinfo is None:
        # Naive datetime - assume it's UTC
        return dt.replace(tzinfo=timezone.utc)
    else:
        # Already timezone-aware
        return dt

def ensure_timezone_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Convert timezone-aware datetime to naive UTC datetime, or return already naive datetime.
    
    Args:
        dt: Datetime to convert (can be None, naive, or aware)
        
    Returns:
        datetime: Timezone-naive UTC datetime or None if input was None
    """
    if dt is None:
        return None
    
    if dt.tzinfo is not None:
        # Timezone-aware - convert to UTC and make naive
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        # Already naive - assume it's UTC
        return dt

def safe_datetime_compare(dt1: Optional[datetime], dt2: Optional[datetime]) -> bool:
    """
    Safely compare two datetimes, handling timezone-aware vs naive mismatches.
    
    Args:
        dt1: First datetime
        dt2: Second datetime
        
    Returns:
        bool: True if dt1 < dt2 (accounting for timezone differences)
    """
    if dt1 is None or dt2 is None:
        return False
    
    # Ensure both are timezone-aware for comparison
    dt1_aware = ensure_timezone_aware(dt1)
    dt2_aware = ensure_timezone_aware(dt2)
    
    return dt1_aware < dt2_aware

def parse_datetime_safe(dt_str: str) -> Optional[datetime]:
    """
    Parse datetime string safely, handling various formats including timezone info.
    
    Args:
        dt_str: Datetime string to parse
        
    Returns:
        datetime: Parsed timezone-aware datetime or None if parsing failed
    """
    if not dt_str:
        return None
    
    try:
        # Handle 'Z' suffix (Zulu time = UTC)
        if dt_str.endswith('Z'):
            dt_str = dt_str.replace('Z', '+00:00')
        
        # Try parsing with timezone info
        dt = datetime.fromisoformat(dt_str)
        return ensure_timezone_aware(dt)
        
    except Exception as e:
        logger.debug(f"Failed to parse datetime string '{dt_str}': {e}")
        return None

def get_cutoff_datetime(days: int, hours: int = 0, minutes: int = 0) -> datetime:
    """
    Get a timezone-aware cutoff datetime for cleanup operations.
    
    Args:
        days: Number of days ago
        hours: Additional hours ago (default: 0)
        minutes: Additional minutes ago (default: 0)
        
    Returns:
        datetime: Timezone-aware cutoff datetime
    """
    delta = timedelta(days=days, hours=hours, minutes=minutes)
    return utcnow_aware() - delta

def format_datetime_for_db(dt: datetime) -> str:
    """
    Format datetime for database storage (ISO format with timezone).
    
    Args:
        dt: Datetime to format
        
    Returns:
        str: ISO formatted datetime string with timezone
    """
    aware_dt = ensure_timezone_aware(dt)
    return aware_dt.isoformat()

def get_minutes_since(dt: Optional[datetime]) -> Optional[int]:
    """
    Get the number of minutes since the given datetime.
    
    Args:
        dt: Datetime to compare against current time
        
    Returns:
        int: Minutes since the datetime, or None if dt is None
    """
    if dt is None:
        return None
    
    now = utcnow_aware()
    dt_aware = ensure_timezone_aware(dt)
    
    delta = now - dt_aware
    return int(delta.total_seconds() / 60)

def to_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """
    Convert datetime to UTC ISO string format for JSON serialization.
    Handles None values gracefully.
    
    Args:
        dt: Datetime to convert (can be None, naive, or aware)
        
    Returns:
        str: ISO formatted UTC datetime string, or None if input was None
    """
    if dt is None:
        return None
    
    aware_dt = ensure_timezone_aware(dt)
    return aware_dt.isoformat() 