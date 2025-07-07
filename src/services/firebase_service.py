import os
import json
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