import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

logger = logging.getLogger(__name__)

class FirebaseService:
    def __init__(self):
        self.db = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK."""
        try:
            if not firebase_admin._apps:
                cred_dict = {
                    "type": os.getenv('FIREBASE_TYPE'),
                    "project_id": os.getenv('FIREBASE_PROJECT_ID'),
                    "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID'),
                    "private_key": os.getenv('FIREBASE_PRIVATE_KEY', '').replace('\\n', '\n'),
                    "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
                    "client_id": os.getenv('FIREBASE_CLIENT_ID'),
                    "auth_uri": os.getenv('FIREBASE_AUTH_URI'),
                    "token_uri": os.getenv('FIREBASE_TOKEN_URI'),
                    "auth_provider_x509_cert_url": os.getenv('FIREBASE_AUTH_PROVIDER_X509_CERT_URL'),
                    "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_X509_CERT_URL')
                }
                
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
            
            self.db = firestore.client()
            logger.info("Firebase initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing Firebase: {e}")
            raise Exception(f"Failed to initialize Firebase: {str(e)}")
    
    async def create_user_if_not_exists(self, user_id: str) -> bool:
        """
        Create a user document if it doesn't exist.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if user was created or already exists
        """
        try:
            user_ref = self.db.collection('users').document(user_id)
            user_doc = user_ref.get()
            
            if not user_doc.exists:
                user_data = {
                    'telegram_id': user_id,
                    'created_at': datetime.now(),
                    'last_active': datetime.now()
                }
                user_ref.set(user_data)
                logger.info(f"Created new user: {user_id}")
            else:
                user_ref.update({'last_active': datetime.now()})
                logger.info(f"Updated last active for user: {user_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error creating/updating user {user_id}: {e}")
            return False
    
    async def save_meal(self, user_id: str, meal_data: Dict) -> Optional[str]:
        """
        Save a meal log to Firestore.
        
        Args:
            user_id: Telegram user ID
            meal_data: Meal information dictionary
            
        Returns:
            Meal document ID if successful, None otherwise
        """
        try:
            meals_ref = self.db.collection('users').document(user_id).collection('meals')
            meal_doc = meals_ref.add(meal_data)
            meal_id = meal_doc[1].id
            
            await self._update_daily_summary(user_id, meal_data)
            
            logger.info(f"Saved meal {meal_id} for user {user_id}")
            return meal_id
            
        except Exception as e:
            logger.error(f"Error saving meal for user {user_id}: {e}")
            return None
    
    async def _update_daily_summary(self, user_id: str, meal_data: Dict):
        """
        Update the daily nutrition summary for a user.
        
        Args:
            user_id: Telegram user ID
            meal_data: Meal information to add to summary
        """
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            summary_ref = self.db.collection('users').document(user_id).collection('summaries').document(today)
            
            nutrition = meal_data.get('nutrition', {})
            
            summary_doc = summary_ref.get()
            if summary_doc.exists:
                current_data = summary_doc.to_dict()
                updated_data = {
                    'total_calories': current_data.get('total_calories', 0) + nutrition.get('calories', 0),
                    'total_protein': current_data.get('total_protein', 0) + nutrition.get('protein', 0),
                    'total_fat': current_data.get('total_fat', 0) + nutrition.get('fat', 0),
                    'total_carbs': current_data.get('total_carbs', 0) + nutrition.get('carbs', 0),
                    'total_fiber': current_data.get('total_fiber', 0) + nutrition.get('fiber', 0),
                    'total_sugar': current_data.get('total_sugar', 0) + nutrition.get('sugar', 0),
                    'total_sodium': current_data.get('total_sodium', 0) + nutrition.get('sodium', 0),
                    'meal_count': current_data.get('meal_count', 0) + 1,
                    'last_updated': datetime.now()
                }
                summary_ref.update(updated_data)
            else:
                new_summary = {
                    'date': today,
                    'total_calories': nutrition.get('calories', 0),
                    'total_protein': nutrition.get('protein', 0),
                    'total_fat': nutrition.get('fat', 0),
                    'total_carbs': nutrition.get('carbs', 0),
                    'total_fiber': nutrition.get('fiber', 0),
                    'total_sugar': nutrition.get('sugar', 0),
                    'total_sodium': nutrition.get('sodium', 0),
                    'meal_count': 1,
                    'created_at': datetime.now(),
                    'last_updated': datetime.now()
                }
                summary_ref.set(new_summary)
            
            logger.info(f"Updated daily summary for user {user_id} on {today}")
            
        except Exception as e:
            logger.error(f"Error updating daily summary for user {user_id}: {e}")
    
    async def get_daily_summary(self, user_id: str, date: str) -> Optional[Dict]:
        """
        Get daily nutrition summary for a user.
        
        Args:
            user_id: Telegram user ID
            date: Date in YYYY-MM-DD format
            
        Returns:
            Daily summary dictionary or None if not found
        """
        try:
            summary_ref = self.db.collection('users').document(user_id).collection('summaries').document(date)
            summary_doc = summary_ref.get()
            
            if summary_doc.exists:
                return summary_doc.to_dict()
            else:
                logger.info(f"No summary found for user {user_id} on {date}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting daily summary for user {user_id} on {date}: {e}")
            return None
    
    async def get_meals_for_date(self, user_id: str, date: str) -> List[Dict]:
        """
        Get all meals for a user on a specific date.
        
        Args:
            user_id: Telegram user ID
            date: Date in YYYY-MM-DD format
            
        Returns:
            List of meal dictionaries
        """
        try:
            start_date = datetime.strptime(date, '%Y-%m-%d')
            end_date = start_date + timedelta(days=1)
            
            meals_ref = self.db.collection('users').document(user_id).collection('meals')
            
            query = meals_ref.where(
                filter=FieldFilter('timestamp', '>=', start_date)
            ).where(
                filter=FieldFilter('timestamp', '<', end_date)
            ).order_by('timestamp')
            
            meals = []
            docs = query.stream()
            
            for doc in docs:
                meal_data = doc.to_dict()
                meal_data['id'] = doc.id
                meals.append(meal_data)
            
            logger.info(f"Retrieved {len(meals)} meals for user {user_id} on {date}")
            return meals
            
        except Exception as e:
            logger.error(f"Error getting meals for user {user_id} on {date}: {e}")
            return []
    
    async def get_recent_meals(self, user_id: str, limit: int = 10) -> List[Dict]:
        """
        Get recent meals for a user.
        
        Args:
            user_id: Telegram user ID
            limit: Maximum number of meals to retrieve
            
        Returns:
            List of recent meal dictionaries
        """
        try:
            meals_ref = self.db.collection('users').document(user_id).collection('meals')
            
            query = meals_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit)
            
            meals = []
            docs = query.stream()
            
            for doc in docs:
                meal_data = doc.to_dict()
                meal_data['id'] = doc.id
                meals.append(meal_data)
            
            logger.info(f"Retrieved {len(meals)} recent meals for user {user_id}")
            return meals
            
        except Exception as e:
            logger.error(f"Error getting recent meals for user {user_id}: {e}")
            return []
    
    async def get_user_stats(self, user_id: str, days: int = 7) -> Dict:
        """
        Get user statistics over a period.
        
        Args:
            user_id: Telegram user ID
            days: Number of days to analyze
            
        Returns:
            Dictionary with user statistics
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            summaries_ref = self.db.collection('users').document(user_id).collection('summaries')
            
            query = summaries_ref.where(
                filter=FieldFilter('created_at', '>=', start_date)
            ).where(
                filter=FieldFilter('created_at', '<=', end_date)
            )
            
            summaries = []
            docs = query.stream()
            
            total_calories = 0
            total_meals = 0
            active_days = 0
            
            for doc in docs:
                summary_data = doc.to_dict()
                summaries.append(summary_data)
                total_calories += summary_data.get('total_calories', 0)
                total_meals += summary_data.get('meal_count', 0)
                active_days += 1
            
            avg_calories_per_day = total_calories / max(active_days, 1)
            avg_meals_per_day = total_meals / max(active_days, 1)
            
            stats = {
                'period_days': days,
                'active_days': active_days,
                'total_calories': total_calories,
                'total_meals': total_meals,
                'avg_calories_per_day': round(avg_calories_per_day, 1),
                'avg_meals_per_day': round(avg_meals_per_day, 1),
                'summaries': summaries
            }
            
            logger.info(f"Retrieved stats for user {user_id} over {days} days")
            return stats
            
        except Exception as e:
            logger.error(f"Error getting user stats for {user_id}: {e}")
            return {}
    
    async def get_meal_by_id(self, user_id: str, meal_id: str) -> Optional[Dict]:
        """
        Get a specific meal by ID.
        
        Args:
            user_id: Telegram user ID
            meal_id: Meal document ID
            
        Returns:
            Meal dictionary or None if not found
        """
        try:
            meal_ref = self.db.collection('users').document(user_id).collection('meals').document(meal_id)
            meal_doc = meal_ref.get()
            
            if meal_doc.exists:
                meal_data = meal_doc.to_dict()
                meal_data['id'] = meal_doc.id
                return meal_data
            else:
                logger.info(f"Meal {meal_id} not found for user {user_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting meal {meal_id} for user {user_id}: {e}")
            return None
    
    async def update_meal(self, user_id: str, meal_id: str, updated_data: Dict) -> bool:
        """
        Update an existing meal.
        
        Args:
            user_id: Telegram user ID
            meal_id: Meal document ID
            updated_data: Updated meal data
            
        Returns:
            True if successful, False otherwise
        """
        try:
            meal_ref = self.db.collection('users').document(user_id).collection('meals').document(meal_id)
            
            # Get original meal data for summary update
            original_meal = meal_ref.get()
            if not original_meal.exists:
                logger.error(f"Meal {meal_id} not found for user {user_id}")
                return False
            
            original_data = original_meal.to_dict()
            
            # Update the meal
            meal_ref.update(updated_data)
            
            # Update daily summary
            await self._update_daily_summary_for_meal_edit(user_id, original_data, updated_data)
            
            logger.info(f"Updated meal {meal_id} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating meal {meal_id} for user {user_id}: {e}")
            return False
    
    async def delete_meal(self, user_id: str, meal_id: str) -> bool:
        """
        Delete a meal by ID.
        
        Args:
            user_id: Telegram user ID
            meal_id: Meal document ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            meal_ref = self.db.collection('users').document(user_id).collection('meals').document(meal_id)
            
            # Get meal data for summary update
            meal_doc = meal_ref.get()
            if not meal_doc.exists:
                logger.error(f"Meal {meal_id} not found for user {user_id}")
                return False
            
            meal_data = meal_doc.to_dict()
            
            # Delete the meal
            meal_ref.delete()
            
            # Update daily summary
            await self._subtract_from_daily_summary(user_id, meal_data)
            
            logger.info(f"Deleted meal {meal_id} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting meal {meal_id} for user {user_id}: {e}")
            return False
    
    async def _update_daily_summary_for_meal_edit(self, user_id: str, original_data: Dict, updated_data: Dict):
        """
        Update daily summary when a meal is edited.
        
        Args:
            user_id: Telegram user ID
            original_data: Original meal data
            updated_data: Updated meal data
        """
        try:
            # Get the date from the original meal
            timestamp = original_data.get('timestamp', datetime.now())
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)
            
            date_str = timestamp.strftime('%Y-%m-%d')
            summary_ref = self.db.collection('users').document(user_id).collection('summaries').document(date_str)
            
            original_nutrition = original_data.get('nutrition', {})
            updated_nutrition = updated_data.get('nutrition', {})
            
            summary_doc = summary_ref.get()
            if summary_doc.exists:
                current_data = summary_doc.to_dict()
                
                # Subtract original nutrition and add updated nutrition
                updated_summary = {
                    'total_calories': current_data.get('total_calories', 0) - original_nutrition.get('calories', 0) + updated_nutrition.get('calories', 0),
                    'total_protein': current_data.get('total_protein', 0) - original_nutrition.get('protein', 0) + updated_nutrition.get('protein', 0),
                    'total_fat': current_data.get('total_fat', 0) - original_nutrition.get('fat', 0) + updated_nutrition.get('fat', 0),
                    'total_carbs': current_data.get('total_carbs', 0) - original_nutrition.get('carbs', 0) + updated_nutrition.get('carbs', 0),
                    'total_fiber': current_data.get('total_fiber', 0) - original_nutrition.get('fiber', 0) + updated_nutrition.get('fiber', 0),
                    'total_sugar': current_data.get('total_sugar', 0) - original_nutrition.get('sugar', 0) + updated_nutrition.get('sugar', 0),
                    'total_sodium': current_data.get('total_sodium', 0) - original_nutrition.get('sodium', 0) + updated_nutrition.get('sodium', 0),
                    'last_updated': datetime.now()
                }
                
                summary_ref.update(updated_summary)
            
            logger.info(f"Updated daily summary for meal edit - user {user_id} on {date_str}")
            
        except Exception as e:
            logger.error(f"Error updating daily summary for meal edit - user {user_id}: {e}")
    
    async def _subtract_from_daily_summary(self, user_id: str, meal_data: Dict):
        """
        Subtract meal data from daily summary.
        
        Args:
            user_id: Telegram user ID
            meal_data: Meal data to subtract
        """
        try:
            timestamp = meal_data.get('timestamp', datetime.now())
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)
            
            date_str = timestamp.strftime('%Y-%m-%d')
            summary_ref = self.db.collection('users').document(user_id).collection('summaries').document(date_str)
            
            nutrition = meal_data.get('nutrition', {})
            
            summary_doc = summary_ref.get()
            if summary_doc.exists:
                current_data = summary_doc.to_dict()
                updated_data = {
                    'total_calories': max(0, current_data.get('total_calories', 0) - nutrition.get('calories', 0)),
                    'total_protein': max(0, current_data.get('total_protein', 0) - nutrition.get('protein', 0)),
                    'total_fat': max(0, current_data.get('total_fat', 0) - nutrition.get('fat', 0)),
                    'total_carbs': max(0, current_data.get('total_carbs', 0) - nutrition.get('carbs', 0)),
                    'total_fiber': max(0, current_data.get('total_fiber', 0) - nutrition.get('fiber', 0)),
                    'total_sugar': max(0, current_data.get('total_sugar', 0) - nutrition.get('sugar', 0)),
                    'total_sodium': max(0, current_data.get('total_sodium', 0) - nutrition.get('sodium', 0)),
                    'meal_count': max(0, current_data.get('meal_count', 0) - 1),
                    'last_updated': datetime.now()
                }
                summary_ref.update(updated_data)
            
            logger.info(f"Subtracted meal from daily summary for user {user_id} on {date_str}")
            
        except Exception as e:
            logger.error(f"Error subtracting from daily summary for user {user_id}: {e}")
    
    async def get_trend_data(self, user_id: str, days: int = 7) -> List[Dict]:
        """
        Get trend data for a user over a specified period.
        
        Args:
            user_id: Telegram user ID
            days: Number of days to analyze
            
        Returns:
            List of daily trend data
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            summaries_ref = self.db.collection('users').document(user_id).collection('summaries')
            
            query = summaries_ref.where(
                filter=FieldFilter('created_at', '>=', start_date)
            ).where(
                filter=FieldFilter('created_at', '<=', end_date)
            ).order_by('date')
            
            trend_data = []
            docs = query.stream()
            
            for doc in docs:
                summary_data = doc.to_dict()
                trend_data.append({
                    'date': summary_data.get('date', ''),
                    'calories': summary_data.get('total_calories', 0),
                    'protein': summary_data.get('total_protein', 0),
                    'carbs': summary_data.get('total_carbs', 0),
                    'fat': summary_data.get('total_fat', 0),
                    'meals': summary_data.get('meal_count', 0)
                })
            
            logger.info(f"Retrieved trend data for user {user_id} over {days} days")
            return trend_data
            
        except Exception as e:
            logger.error(f"Error getting trend data for user {user_id}: {e}")
            return []
    
    async def save_access_request(self, user_id: str, username: str = None, first_name: str = None, last_name: str = None) -> bool:
        """
        Save an access request to access_requests collection.

        Args:
            user_id: Telegram user ID
            username: Telegram username (optional)
            first_name: User's first name (optional)
            last_name: User's last name (optional)

        Returns:
            True if request was saved successfully, False otherwise
        """
        try:
            # Check if user already has a pending or approved request
            access_requests_ref = self.db.collection('access_requests').document(user_id)
            access_requests_doc = access_requests_ref.get()

            if access_requests_doc.exists:
                request_data = access_requests_doc.to_dict()
                current_status = request_data.get('status')
                if current_status in ['pending', 'approved']:
                    logger.info(f"User {user_id} already has access request with status: {current_status}")
                    return False

            # Create display name
            display_name = self._format_display_name(username, first_name, last_name)

            # Save access request
            request_data = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
                'display_name': display_name,
                'status': 'pending',
                'requested_at': datetime.now(),
            }

            access_requests_ref.set(request_data, merge=True)

            logger.info(f"Access request saved for user {user_id} ({display_name})")
            return True

        except Exception as e:
            logger.error(f"Error saving access request for user {user_id}: {e}")
            return False
    
    async def get_access_request(self, user_id: str) -> Optional[Dict]:
        """
        Get an access request by user ID.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Access request dictionary or None if not found
        """
        try:
            request_ref = self.db.collection('access_requests').document(user_id)
            request_doc = request_ref.get()
            
            if request_doc.exists:
                return request_doc.to_dict()
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting access request for user {user_id}: {e}")
            return None
    
    async def get_all_access_requests(self, status: str = None) -> List[Dict]:
        """
        Get all access requests.
        
        Args:
            status: Filter by status ('pending', 'approved', 'denied') or None for all
            
        Returns:
            List of access request dictionaries
        """
        try:
            requests_ref = self.db.collection('access_requests')
            
            if status:
                query = requests_ref.where(filter=FieldFilter('status', '==', status))
            else:
                query = requests_ref
            
            query = query.order_by('requested_at', direction=firestore.Query.DESCENDING)
            
            requests = []
            docs = query.stream()
            
            for doc in docs:
                request_data = doc.to_dict()
                request_data['id'] = doc.id
                requests.append(request_data)
            
            logger.info(f"Retrieved {len(requests)} access requests (status: {status or 'all'})")
            return requests
            
        except Exception as e:
            logger.error(f"Error getting access requests: {e}")
            return []
    
    async def update_access_requests_status(self, user_id: str, status: str) -> bool:
        """
        Update the status of an access request.
        
        Args:
            user_id: Telegram user ID
            status: New status ('pending', 'approved', 'denied')
            
        Returns:
            True if successful, False otherwise
        """
        try:
            request_ref = self.db.collection('access_requests').document(user_id)
            request_ref.update({
                'status': status,
                'updated_at': datetime.now()
            })
            
            logger.info(f"Updated access request status for user {user_id} to {status}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating access request status for user {user_id}: {e}")
            return False
    
    def _format_display_name(self, username: str = None, first_name: str = None, last_name: str = None) -> str:
        """
        Format a display name from available user information.
        
        Args:
            username: Telegram username (optional)
            first_name: User's first name (optional)
            last_name: User's last name (optional)
            
        Returns:
            Formatted display name
        """
        parts = []
        
        if first_name:
            parts.append(first_name)
        if last_name:
            parts.append(last_name)
        
        name = " ".join(parts) if parts else "Unknown"
        
        if username:
            name += f" (@{username})"

        return name

    async def get_authorized_users(self) -> List[str]:
        """
        Get list of authorized user IDs from access_requests collection.

        Returns:
            List of authorized user IDs
        """
        try:
            access_requests_ref = self.db.collection('access_requests')
            query = access_requests_ref.where(filter=FieldFilter('status', '==', 'approved'))
            docs = query.stream()

            user_ids = []
            for doc in docs:
                request_data = doc.to_dict()
                user_id = request_data.get('user_id')
                if user_id:
                    user_ids.append(user_id)

            logger.info(f"Retrieved {len(user_ids)} authorized users from Firebase access_requests collection")
            return user_ids

        except Exception as e:
            logger.error(f"Error getting authorized users from Firebase: {e}")
            return []

    async def approve_user_access(self, user_id: str, approved_by: str = None) -> bool:
        """
        Approve user access by updating their status in access_requests collection
        and ensuring user details are stored in users collection.

        Args:
            user_id: Telegram user ID to approve
            approved_by: User ID of admin who approved this user

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get the access request details first
            access_requests_ref = self.db.collection('access_requests').document(user_id)
            access_requests_doc = access_requests_ref.get()

            if not access_requests_doc.exists:
                logger.error(f"No access request found for user {user_id}")
                return False

            request_data = access_requests_doc.to_dict()

            # Update the access request status to approved
            access_requests_ref.update({
                'status': 'approved',
                'approved_at': datetime.now(),
                'approved_by': approved_by
            })

            # Store/update user details in users collection for data preservation
            user_ref = self.db.collection('users').document(user_id)
            user_data = {
                'telegram_id': user_id,
                'username': request_data.get('username'),
                'first_name': request_data.get('first_name'),
                'last_name': request_data.get('last_name'),
                'last_active': datetime.now(),
                'created_at': datetime.now()
            }

            # Check if user already exists to preserve created_at
            existing_user = user_ref.get()
            if existing_user.exists:
                existing_data = existing_user.to_dict()
                user_data['created_at'] = existing_data.get('created_at', datetime.now())
                user_ref.update(user_data)
            else:
                user_ref.set(user_data)

            logger.info(f"Approved access for user {user_id} (approved by {approved_by})")
            return True

        except Exception as e:
            logger.error(f"Error approving user {user_id}: {e}")
            return False

    async def revoke_user_access(self, user_id: str, revoked_by: str = None) -> bool:
        """
        Revoke user access by updating their status in access_requests collection.
        User data remains in users collection for data preservation.

        Args:
            user_id: Telegram user ID to revoke access
            revoked_by: User ID of admin who revoked this user

        Returns:
            True if successful, False otherwise
        """
        try:
            # Update the access request status to revoked
            access_requests_ref = self.db.collection('access_requests').document(user_id)
            access_requests_doc = access_requests_ref.get()

            if access_requests_doc.exists:
                access_requests_ref.update({
                    'status': 'revoked',
                    'revoked_at': datetime.now(),
                    'revoked_by': revoked_by
                })

                logger.info(f"Revoked access for user {user_id} (revoked by {revoked_by})")
                return True
            else:
                logger.warning(f"Access request for user {user_id} not found when trying to revoke access")
                return False

        except Exception as e:
            logger.error(f"Error revoking access for user {user_id}: {e}")
            return False

    async def add_authorized_user(self, user_id: str, added_by: str = None) -> bool:
        """
        Add a user by creating an approved access request and user record.

        Args:
            user_id: Telegram user ID to add
            added_by: User ID of admin who added this user

        Returns:
            True if successful, False otherwise
        """
        try:
            # Create access request record with approved status
            access_requests_ref = self.db.collection('access_requests').document(user_id)
            request_data = {
                'user_id': user_id,
                'username': None,  # Will be filled when user interacts
                'first_name': None,
                'last_name': None,
                'display_name': f'User {user_id}',
                'status': 'approved',
                'requested_at': datetime.now(),
                'approved_at': datetime.now(),
                'approved_by': added_by
            }
            access_requests_ref.set(request_data)

            # Create user record in users collection
            user_ref = self.db.collection('users').document(user_id)
            user_data = {
                'telegram_id': user_id,
                'username': None,
                'first_name': None,
                'last_name': None,
                'created_at': datetime.now(),
                'last_active': datetime.now()
            }
            user_ref.set(user_data)

            logger.info(f"Added authorized user {user_id} (added by {added_by})")
            return True

        except Exception as e:
            logger.error(f"Error adding authorized user {user_id}: {e}")
            return False

    async def get_access_requests(self, status: str = 'pending') -> List[Dict]:
        """
        Get access requests from access_requests collection.

        Args:
            status: Filter by status ('pending', 'approved', 'denied', 'revoked') or None for all

        Returns:
            List of user dictionaries with access request info
        """
        try:
            access_requests_ref = self.db.collection('access_requests')

            if status:
                query = access_requests_ref.where(filter=FieldFilter('status', '==', status))
                # Note: Cannot order_by different field when filtering without composite index
                # Results will be retrieved and sorted in Python instead
            else:
                query = access_requests_ref.order_by('requested_at', direction=firestore.Query.DESCENDING)

            requests = []
            docs = query.stream()

            for doc in docs:
                request_data = doc.to_dict()

                # Format the request data to match expected structure
                formatted_data = {
                    'user_id': request_data.get('user_id'),
                    'username': request_data.get('username'),
                    'first_name': request_data.get('first_name'),
                    'last_name': request_data.get('last_name'),
                    'display_name': request_data.get('display_name') or self._format_display_name(
                        request_data.get('username'),
                        request_data.get('first_name'),
                        request_data.get('last_name')
                    ),
                    'access_status': request_data.get('status', 'pending'),  # Map 'status' to 'access_status'
                    'requested_at': request_data.get('requested_at'),
                    'approved_at': request_data.get('approved_at'),
                    'approved_by': request_data.get('approved_by'),
                    'revoked_at': request_data.get('revoked_at'),
                    'revoked_by': request_data.get('revoked_by')
                }

                requests.append(formatted_data)

            # Sort by requested_at in descending order when filtering by status
            if status:
                requests.sort(key=lambda x: x.get('requested_at') or datetime.min, reverse=True)

            logger.info(f"Retrieved {len(requests)} access requests (status: {status or 'all'})")
            return requests

        except Exception as e:
            logger.error(f"Error getting access requests: {e}")
            return []

    async def get_all_users_with_access_info(self) -> List[Dict]:
        """
        Get all users with their access status information from access_requests collection.

        Returns:
            List of user dictionaries with access info
        """
        try:
            # Get all access requests (all statuses)
            all_requests = await self.get_access_requests(status=None)
            return all_requests

        except Exception as e:
            logger.error(f"Error getting all users with access info: {e}")
            return []

    async def migrate_env_users_to_firebase(self) -> int:
        """
        Migrate users from environment variable to Firebase.

        Returns:
            Number of users migrated
        """
        try:
            # Get users from environment variable
            authorized_users_str = os.getenv('AUTHORIZED_TELEGRAM_IDS', '')
            if not authorized_users_str:
                logger.info("No users found in environment variable to migrate")
                return 0

            user_ids = [uid.strip() for uid in authorized_users_str.split(',') if uid.strip()]
            migrated_count = 0

            for user_id in user_ids:
                # Check if user already exists in Firebase
                existing_user = await self._get_authorized_user(user_id)
                if not existing_user:
                    success = await self.add_authorized_user(user_id, "system_migration")
                    if success:
                        migrated_count += 1

            logger.info(f"Migrated {migrated_count} users from environment to Firebase")
            return migrated_count

        except Exception as e:
            logger.error(f"Error migrating users to Firebase: {e}")
            return 0

    async def _get_authorized_user(self, user_id: str) -> Optional[Dict]:
        """Get a specific authorized user by ID."""
        try:
            user_ref = self.db.collection('authorized_users').document(user_id)
            user_doc = user_ref.get()

            if user_doc.exists:
                return user_doc.to_dict()
            else:
                return None

        except Exception as e:
            logger.error(f"Error getting authorized user {user_id}: {e}")
            return None

    async def migrate_users_to_access_requests(self) -> Dict[str, int]:
        """
        Migrate user access requests from users collection to access_requests collection.

        Returns:
            Dictionary with migration statistics
        """
        try:
            logger.info("Starting migration from users collection to access_requests collection...")

            # Get all users from the users collection
            users_ref = self.db.collection('users')
            docs = users_ref.stream()

            migrated_count = 0
            skipped_count = 0
            error_count = 0

            for doc in docs:
                try:
                    user_data = doc.to_dict()
                    user_id = doc.id

                    # Skip if this is already an authorized user (has last_active, created_at, etc.)
                    if user_data.get('last_active') or user_data.get('created_at'):
                        logger.info(f"Skipping user {user_id} - appears to be a regular user, not a request")
                        skipped_count += 1
                        continue

                    # Check if this looks like an access request (has username, first_name, etc. but no activity)
                    if not user_data.get('telegram_id') and not user_data.get('username') and not user_data.get('first_name'):
                        logger.info(f"Skipping user {user_id} - doesn't look like an access request")
                        skipped_count += 1
                        continue

                    # Check if request already exists in access_requests
                    existing_request = await self.get_access_requests(user_id)
                    if existing_request:
                        logger.info(f"Skipping user {user_id} - already exists in access_requests")
                        skipped_count += 1
                        continue

                    # Create access request from user data
                    username = user_data.get('username')
                    first_name = user_data.get('first_name', user_data.get('firstname'))
                    last_name = user_data.get('last_name', user_data.get('lastname'))

                    # Create display name
                    display_name = self._format_display_name(username, first_name, last_name)

                    # Create access request
                    request_data = {
                        'user_id': user_id,
                        'username': username,
                        'first_name': first_name,
                        'last_name': last_name,
                        'display_name': display_name,
                        'requested_at': user_data.get('timestamp', datetime.now()),
                        'status': 'pending'
                    }

                    # Save to access_requests collection
                    access_requests_ref = self.db.collection('access_requests').document(user_id)
                    access_requests_ref.set(request_data)

                    logger.info(f"Migrated user {user_id} ({display_name}) to access_requests")
                    migrated_count += 1

                except Exception as e:
                    logger.error(f"Error migrating user {doc.id}: {e}")
                    error_count += 1

            result = {
                'migrated': migrated_count,
                'skipped': skipped_count,
                'errors': error_count,
                'total_processed': migrated_count + skipped_count + error_count
            }

            logger.info(f"Migration completed: {result}")
            return result

        except Exception as e:
            logger.error(f"Error during users to access_requests migration: {e}")
            return {'migrated': 0, 'skipped': 0, 'errors': 1, 'total_processed': 0}

    async def inspect_users_collection(self) -> Dict:
        """
        Inspect the users collection to understand the data structure.

        Returns:
            Dictionary with sample data and statistics
        """
        try:
            logger.info("Inspecting users collection...")

            users_ref = self.db.collection('users')
            docs = users_ref.limit(10).stream()  # Get first 10 users as sample

            sample_users = []
            total_count = 0

            for doc in docs:
                user_data = doc.to_dict()
                user_id = doc.id

                # Anonymize the data for inspection
                sample_data = {
                    'user_id': user_id,
                    'has_username': bool(user_data.get('username')),
                    'has_first_name': bool(user_data.get('first_name') or user_data.get('firstname')),
                    'has_last_name': bool(user_data.get('last_name') or user_data.get('lastname')),
                    'has_telegram_id': bool(user_data.get('telegram_id')),
                    'has_created_at': bool(user_data.get('created_at')),
                    'has_last_active': bool(user_data.get('last_active')),
                    'has_timestamp': bool(user_data.get('timestamp')),
                    'fields': list(user_data.keys())
                }

                sample_users.append(sample_data)
                total_count += 1

            # Get total count
            try:
                total_docs = len(list(users_ref.stream()))
            except:
                total_docs = "unknown"

            result = {
                'total_users': total_docs,
                'sample_count': total_count,
                'sample_users': sample_users
            }

            logger.info(f"Users collection inspection: {total_docs} total users, {total_count} sampled")
            return result

        except Exception as e:
            logger.error(f"Error inspecting users collection: {e}")
            return {'error': str(e)}