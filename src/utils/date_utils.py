from datetime import datetime, timedelta
from typing import List, Tuple

def get_date_range(days: int) -> Tuple[datetime, datetime]:
    """
    Get date range for the specified number of days.
    
    Args:
        days: Number of days to look back
        
    Returns:
        Tuple of (start_date, end_date)
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    return start_date, end_date

def get_week_dates() -> List[str]:
    """
    Get list of dates for the current week.
    
    Returns:
        List of date strings in YYYY-MM-DD format
    """
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())
    
    dates = []
    for i in range(7):
        date = week_start + timedelta(days=i)
        dates.append(date.strftime('%Y-%m-%d'))
    
    return dates

def get_recent_dates(days: int = 7) -> List[str]:
    """
    Get list of recent dates.
    
    Args:
        days: Number of recent days to get
        
    Returns:
        List of date strings in YYYY-MM-DD format
    """
    dates = []
    today = datetime.now()
    
    for i in range(days):
        date = today - timedelta(days=i)
        dates.append(date.strftime('%Y-%m-%d'))
    
    return dates

def format_date_display(date_str: str) -> str:
    """
    Format date string for display.
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        
    Returns:
        Formatted date string
    """
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
        today = datetime.now().date()
        
        if date.date() == today:
            return "Today"
        elif date.date() == today - timedelta(days=1):
            return "Yesterday"
        elif date.date() == today - timedelta(days=2):
            return "2 days ago"
        else:
            return date.strftime('%b %d')
    except ValueError:
        return date_str

def is_today(date_str: str) -> bool:
    """
    Check if date string is today.
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        
    Returns:
        True if date is today
    """
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        return date == datetime.now().date()
    except ValueError:
        return False

def days_ago(date_str: str) -> int:
    """
    Calculate how many days ago a date was.
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        
    Returns:
        Number of days ago (0 for today, 1 for yesterday, etc.)
    """
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        today = datetime.now().date()
        return (today - date).days
    except ValueError:
        return 0