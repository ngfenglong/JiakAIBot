import os
import logging
import aiohttp
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class NutritionixService:
    def __init__(self):
        self.app_id = os.getenv('NUTRITIONIX_APP_ID')
        self.api_key = os.getenv('NUTRITIONIX_API_KEY')
        self.base_url = "https://trackapi.nutritionix.com/v2"
        
        if not self.app_id or not self.api_key:
            logger.error("Nutritionix credentials not found in environment variables")
    
    async def get_nutrition_data(self, food_description: str, portion_multiplier: float = 1.0) -> Dict:
        """
        Get nutrition data for a food description from Nutritionix API.

        Args:
            food_description: Description of the food item(s)
            portion_multiplier: Multiplier to adjust nutrition values (e.g., 1.5 for 1.5x portion)

        Returns:
            Dictionary containing nutrition information with portion adjustments
        """
        try:
            headers = {
                'x-app-id': self.app_id,
                'x-app-key': self.api_key,
                'Content-Type': 'application/json'
            }
            
            payload = {
                'query': food_description,
                'timezone': 'US/Eastern'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/natural/nutrients",
                    headers=headers,
                    json=payload
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        return self._process_nutrition_data(data, portion_multiplier)
                    else:
                        error_text = await response.text()
                        logger.error(f"Nutritionix API error: {response.status} - {error_text}")
                        raise Exception(f"Nutritionix API error: {response.status}")
                        
        except Exception as e:
            logger.error(f"Error getting nutrition data: {e}")
            return self._get_default_nutrition_data()
    
    def _process_nutrition_data(self, data: Dict, portion_multiplier: float = 1.0) -> Dict:
        """
        Process raw Nutritionix API response into simplified nutrition data.

        Args:
            data: Raw API response data
            portion_multiplier: Multiplier to adjust nutrition values

        Returns:
            Simplified nutrition dictionary with portion adjustments
        """
        try:
            foods = data.get('foods', [])
            
            if not foods:
                return self._get_default_nutrition_data()
            
            total_calories = 0
            total_protein = 0
            total_carbs = 0
            total_fat = 0
            total_fiber = 0
            total_sugar = 0
            total_sodium = 0
            
            food_items = []
            
            for food in foods:
                calories = food.get('nf_calories', 0) or 0
                protein = food.get('nf_protein', 0) or 0
                carbs = food.get('nf_total_carbohydrate', 0) or 0
                fat = food.get('nf_total_fat', 0) or 0
                fiber = food.get('nf_dietary_fiber', 0) or 0
                sugar = food.get('nf_sugars', 0) or 0
                sodium = food.get('nf_sodium', 0) or 0
                
                total_calories += calories
                total_protein += protein
                total_carbs += carbs
                total_fat += fat
                total_fiber += fiber
                total_sugar += sugar
                total_sodium += sodium
                
                food_items.append({
                    'name': food.get('food_name', 'Unknown'),
                    'serving_qty': food.get('serving_qty', 1),
                    'serving_unit': food.get('serving_unit', 'serving'),
                    'calories': calories,
                    'protein': protein,
                    'carbs': carbs,
                    'fat': fat
                })
            
            # Apply portion multiplier to totals
            adjusted_calories = total_calories * portion_multiplier
            adjusted_protein = total_protein * portion_multiplier
            adjusted_carbs = total_carbs * portion_multiplier
            adjusted_fat = total_fat * portion_multiplier
            adjusted_fiber = total_fiber * portion_multiplier
            adjusted_sugar = total_sugar * portion_multiplier
            adjusted_sodium = total_sodium * portion_multiplier

            nutrition_data = {
                'calories': round(adjusted_calories, 1),
                'protein': round(adjusted_protein, 1),
                'carbs': round(adjusted_carbs, 1),
                'fat': round(adjusted_fat, 1),
                'fiber': round(adjusted_fiber, 1),
                'sugar': round(adjusted_sugar, 1),
                'sodium': round(adjusted_sodium, 1),
                'food_items': food_items,
                'total_items': len(foods),
                'portion_multiplier': portion_multiplier,
                'raw_nutrition': {
                    'calories': round(total_calories, 1),
                    'protein': round(total_protein, 1),
                    'carbs': round(total_carbs, 1),
                    'fat': round(total_fat, 1),
                    'fiber': round(total_fiber, 1),
                    'sugar': round(total_sugar, 1),
                    'sodium': round(total_sodium, 1)
                }
            }
            
            logger.info(f"Processed nutrition data: {nutrition_data}")
            return nutrition_data
            
        except Exception as e:
            logger.error(f"Error processing nutrition data: {e}")
            return self._get_default_nutrition_data()
    
    def _get_default_nutrition_data(self) -> Dict:
        """
        Return default nutrition data when API fails.
        
        Returns:
            Default nutrition dictionary
        """
        return {
            'calories': 0,
            'protein': 0,
            'carbs': 0,
            'fat': 0,
            'fiber': 0,
            'sugar': 0,
            'sodium': 0,
            'food_items': [],
            'total_items': 0,
            'error': 'Unable to retrieve nutrition data'
        }
    
    async def search_food(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Search for food items in Nutritionix database.
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            List of food items matching the search
        """
        try:
            headers = {
                'x-app-id': self.app_id,
                'x-app-key': self.api_key
            }
            
            params = {
                'query': query,
                'limit': limit
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/search/instant",
                    headers=headers,
                    params=params
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        return self._process_search_results(data)
                    else:
                        logger.error(f"Nutritionix search error: {response.status}")
                        return []
                        
        except Exception as e:
            logger.error(f"Error searching food: {e}")
            return []
    
    def _process_search_results(self, data: Dict) -> List[Dict]:
        """
        Process search results from Nutritionix API.
        
        Args:
            data: Raw search results
            
        Returns:
            Processed list of food items
        """
        try:
            results = []
            
            common_foods = data.get('common', [])
            branded_foods = data.get('branded', [])
            
            for food in common_foods:
                results.append({
                    'name': food.get('food_name', ''),
                    'type': 'common',
                    'image': food.get('photo', {}).get('thumb', ''),
                    'tag_id': food.get('tag_id', '')
                })
            
            for food in branded_foods:
                results.append({
                    'name': food.get('food_name', ''),
                    'type': 'branded',
                    'brand': food.get('brand_name', ''),
                    'image': food.get('photo', {}).get('thumb', ''),
                    'nix_item_id': food.get('nix_item_id', '')
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Error processing search results: {e}")
            return []