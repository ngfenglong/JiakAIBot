import os
import logging
from datetime import datetime
from typing import Set, Optional, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

class AccessControl:
    """Manages user access permissions for the JiakAI bot."""
    
    def __init__(self):
        self.authorized_users: Set[str] = set()
        self.access_requests_file = "access_requests.txt"
        self._load_authorized_users()
    
    def _load_authorized_users(self):
        """Load authorized users from environment variable."""
        try:
            # Get authorized users from .env file
            authorized_users_str = os.getenv('AUTHORIZED_TELEGRAM_IDS', '')
            print('authorized_users_str - ',authorized_users_str)
            
            if authorized_users_str:
                # Split by comma and clean up whitespace
                user_ids = [uid.strip() for uid in authorized_users_str.split(',') if uid.strip()]
                self.authorized_users = set(user_ids)
                logger.info(f"Loaded {len(self.authorized_users)} authorized users: {list(self.authorized_users)}")
            else:
                # Clear authorized users if env var is empty
                self.authorized_users = set()
                logger.warning("No authorized users found in AUTHORIZED_TELEGRAM_IDS environment variable - access denied to all users")
                
        except Exception as e:
            logger.error(f"Error loading authorized users: {e}")
            # On error, clear authorized users for security
            self.authorized_users = set()
    
    def reload_authorized_users(self):
        """Manually reload authorized users from environment."""
        self._load_authorized_users()
        return len(self.authorized_users)
    
    def is_authorized(self, user_id: str) -> bool:
        """
        Check if a user is authorized to use the bot.
        
        Args:
            user_id: Telegram user ID as string
            
        Returns:
            True if user is authorized, False otherwise
        """
        # Reload authorized users each time to get fresh env vars
        self._load_authorized_users()
        return user_id in self.authorized_users
    
    def request_access(self, user_id: str, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None) -> bool:
        """
        Log an access request from a user.
        
        Args:
            user_id: Telegram user ID
            username: Telegram username (optional)
            first_name: User's first name (optional)
            last_name: User's last name (optional)
            
        Returns:
            True if request was logged successfully, False otherwise
        """
        try:
            # Check if user is already authorized
            if self.is_authorized(user_id):
                logger.info(f"User {user_id} is already authorized, ignoring access request")
                return False
            
            # Check if user has already requested access
            if self._has_existing_request(user_id):
                logger.info(f"User {user_id} has already requested access")
                return False
            
            # Log the access request
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            display_name = self._format_display_name(username, first_name, last_name)
            
            request_line = f"{timestamp} | ID: {user_id} | Name: {display_name}\n"
            
            # Append to access requests file
            with open(self.access_requests_file, 'a', encoding='utf-8') as f:
                f.write(request_line)
            
            logger.info(f"Access request logged for user {user_id} ({display_name})")
            return True
            
        except Exception as e:
            logger.error(f"Error logging access request for user {user_id}: {e}")
            return False
    
    def _has_existing_request(self, user_id: str) -> bool:
        """Check if user has already made an access request."""
        try:
            if not os.path.exists(self.access_requests_file):
                return False
            
            with open(self.access_requests_file, 'r', encoding='utf-8') as f:
                content = f.read()
                return f"ID: {user_id}" in content
                
        except Exception as e:
            logger.error(f"Error checking existing requests: {e}")
            return False
    
    def _format_display_name(self, username: Optional[str], first_name: Optional[str], last_name: Optional[str]) -> str:
        """Format a display name from available user information."""
        parts = []
        
        if first_name:
            parts.append(first_name)
        if last_name:
            parts.append(last_name)
        
        name = " ".join(parts) if parts else "Unknown"
        
        if username:
            name += f" (@{username})"
        
        return name
    
    def get_authorization_status(self, user_id: str) -> Dict[str, any]:
        """
        Get detailed authorization status for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dictionary with authorization details
        """
        is_auth = self.is_authorized(user_id)
        has_requested = self._has_existing_request(user_id) if not is_auth else False
        
        return {
            'is_authorized': is_auth,
            'has_requested_access': has_requested,
            'total_authorized_users': len(self.authorized_users)
        }
    
    def get_access_requests_count(self) -> int:
        """Get the total number of access requests."""
        try:
            if not os.path.exists(self.access_requests_file):
                return 0
            
            with open(self.access_requests_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                return len([line for line in lines if line.strip()])
                
        except Exception as e:
            logger.error(f"Error counting access requests: {e}")
            return 0

# Global instance
access_control = AccessControl()

def check_user_access(user_id: str) -> bool:
    """
    Convenience function to check if user has access.
    
    Args:
        user_id: Telegram user ID as string
        
    Returns:
        True if user is authorized
    """
    return access_control.is_authorized(user_id)

def log_access_request(user_id: str, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None) -> bool:
    """
    Convenience function to log an access request.
    
    Args:
        user_id: Telegram user ID
        username: Telegram username (optional)
        first_name: User's first name (optional)
        last_name: User's last name (optional)
        
    Returns:
        True if request was logged successfully
    """
    return access_control.request_access(user_id, username, first_name, last_name)

def reload_authorized_users() -> int:
    """
    Convenience function to reload authorized users from environment.
    
    Returns:
        Number of authorized users loaded
    """
    return access_control.reload_authorized_users()