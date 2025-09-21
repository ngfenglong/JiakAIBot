import os
import logging
from datetime import datetime, timedelta
from typing import Set, Optional, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

class AccessControl:
    """Manages user access permissions for the JiakAI bot."""

    def __init__(self, firebase_service=None):
        self.authorized_users: Set[str] = set()
        self.firebase_service = firebase_service
        self.cache_ttl = 300  # 5 minutes in seconds
        self.last_cache_update = None
        self._load_authorized_users()
    
    def _load_authorized_users(self):
        """Load authorized users from environment variable (sync initialization)."""
        try:
            # For initialization, always use environment variable
            # Firebase loading will be done asynchronously when needed
            self._load_from_env()

        except Exception as e:
            logger.error(f"Error loading authorized users: {e}")
            # On error, clear authorized users for security
            self.authorized_users = set()

    async def _load_from_firebase(self):
        """Load authorized users from Firebase."""
        try:
            authorized_users = await self.firebase_service.get_authorized_users()
            if authorized_users:
                self.authorized_users = set(authorized_users)
                self.last_cache_update = datetime.now()
                logger.info(f"Loaded {len(self.authorized_users)} authorized users from Firebase")
            else:
                logger.warning("No authorized users found in Firebase - falling back to environment variable")
                self._load_from_env()

        except Exception as e:
            logger.error(f"Error loading authorized users from Firebase: {e}")
            self._load_from_env()

    def _load_from_env(self):
        """Load authorized users from environment variable (fallback method)."""
        try:
            # Get authorized users from .env file
            authorized_users_str = os.getenv('AUTHORIZED_TELEGRAM_IDS', '')
            print('authorized_users_str - ', authorized_users_str)

            if authorized_users_str:
                # Split by comma and clean up whitespace
                user_ids = [uid.strip() for uid in authorized_users_str.split(',') if uid.strip()]
                self.authorized_users = set(user_ids)
                logger.info(f"Loaded {len(self.authorized_users)} authorized users from environment: {list(self.authorized_users)}")
            else:
                # Clear authorized users if env var is empty
                self.authorized_users = set()
                logger.warning("No authorized users found in AUTHORIZED_TELEGRAM_IDS environment variable - access denied to all users")

        except Exception as e:
            logger.error(f"Error loading authorized users from environment: {e}")
            # On error, clear authorized users for security
            self.authorized_users = set()
    
    async def reload_authorized_users(self):
        """Manually reload authorized users."""
        if self.firebase_service:
            await self._load_from_firebase()
        else:
            self._load_from_env()
        return len(self.authorized_users)

    async def is_authorized(self, user_id: str) -> bool:
        """
        Check if a user is authorized to use the bot with cache management.

        Args:
            user_id: Telegram user ID as string

        Returns:
            True if user is authorized, False otherwise
        """
        # Check if cache needs refresh (only for Firebase)
        if (self.firebase_service and self.last_cache_update and
            (datetime.now() - self.last_cache_update).seconds > self.cache_ttl):
            logger.info("Cache expired, refreshing authorized users from Firebase")
            await self._load_from_firebase()
        elif not self.firebase_service:
            # For environment variable method, always reload to get fresh values
            self._load_from_env()

        return user_id in self.authorized_users

    # Synchronous version for backwards compatibility
    def is_authorized_sync(self, user_id: str) -> bool:
        """
        Synchronous version of is_authorized for backwards compatibility.
        Only uses environment variables (no Firebase cache refresh).
        """
        if not self.firebase_service:
            self._load_from_env()
        return user_id in self.authorized_users
    
    async def request_access(self, user_id: str, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None) -> bool:
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
            if await self.is_authorized(user_id):
                logger.info(f"User {user_id} is already authorized, ignoring access request")
                return False
            
            # Check if user has already requested access
            if await self._has_existing_request(user_id):
                logger.info(f"User {user_id} has already requested access")
                return False
            
            # Save access request to Firebase
            if self.firebase_service:
                success = await self.firebase_service.save_access_request(
                    user_id, username, first_name, last_name
                )
                if success:
                    display_name = self._format_display_name(username, first_name, last_name)
                    logger.info(f"Access request saved to Firebase for user {user_id} ({display_name})")
                    return True
                else:
                    logger.error(f"Failed to save access request to Firebase for user {user_id}")
                    return False
            else:
                logger.error("Firebase service not available for access request logging")
                return False
            
        except Exception as e:
            logger.error(f"Error logging access request for user {user_id}: {e}")
            return False
    
    async def _has_existing_request(self, user_id: str) -> bool:
        """Check if user has already made an access request."""
        try:
            if self.firebase_service:
                existing_request = await self.firebase_service.get_access_request(user_id)
                return existing_request is not None
            else:
                logger.error("Firebase service not available for checking existing requests")
                return False
                
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
    
    async def get_authorization_status(self, user_id: str) -> Dict[str, any]:
        """
        Get detailed authorization status for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dictionary with authorization details
        """
        is_auth = self.is_authorized(user_id)
        has_requested = await self._has_existing_request(user_id) if not is_auth else False
        
        return {
            'is_authorized': is_auth,
            'has_requested_access': has_requested,
            'total_authorized_users': len(self.authorized_users)
        }
    
    async def get_access_requests_count(self) -> int:
        """Get the total number of access requests."""
        try:
            if self.firebase_service:
                requests = await self.firebase_service.get_all_access_requests()
                return len(requests)
            else:
                logger.error("Firebase service not available for counting access requests")
                return 0
                
        except Exception as e:
            logger.error(f"Error counting access requests: {e}")
            return 0

# Global instance - will be initialized with Firebase service in main.py
access_control = None

def check_user_access(user_id: str) -> bool:
    """
    Convenience function to check if user has access (synchronous version).

    Args:
        user_id: Telegram user ID as string

    Returns:
        True if user is authorized
    """
    if access_control:
        return access_control.is_authorized_sync(user_id)
    else:
        logger.error("Access control not initialized")
        return False

async def check_user_access_async(user_id: str) -> bool:
    """
    Convenience function to check if user has access (async version with Firebase support).

    Args:
        user_id: Telegram user ID as string

    Returns:
        True if user is authorized
    """
    if access_control:
        return await access_control.is_authorized(user_id)
    else:
        logger.error("Access control not initialized")
        return False

async def log_access_request(user_id: str, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None) -> bool:
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
    if access_control:
        return await access_control.request_access(user_id, username, first_name, last_name)
    else:
        logger.error("Access control not initialized")
        return False

async def reload_authorized_users() -> int:
    """
    Convenience function to reload authorized users.

    Returns:
        Number of authorized users loaded
    """
    if access_control:
        return await access_control.reload_authorized_users()
    else:
        logger.error("Access control not initialized")
        return 0