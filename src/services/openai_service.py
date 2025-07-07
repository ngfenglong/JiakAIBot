import os
import base64
import logging
import re
from openai import AsyncOpenAI
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class OpenAIService:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.getenv('OPENAI_API_KEY')
        )
        self.model = os.getenv('OPENAI_MODEL', 'gpt-4o')
    
    async def analyze_food_image(self, image_path: str) -> Dict[str, any]:
        """
        Analyze a food image using OpenAI Vision API.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dictionary with 'success', 'description', 'confidence', and 'error' keys
        """
        try:
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a nutrition expert analyzing food photos. Focus ONLY on actual food items that people eat. "
                            "IGNORE plates, bowls, utensils, tables, bamboo mats, decorative items, drinks, and background objects. "
                            "Provide realistic portion estimates based on typical serving sizes. "
                            "If you see multiple portions of the same food, specify the total amount. "
                            "Be conservative with portion estimates - it's better to underestimate than overestimate. "
                            "If NO FOOD is visible or you cannot identify any food items clearly, respond with 'NO_FOOD_DETECTED'."
                        )
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Analyze this food photo and list ONLY the edible food items with realistic portion sizes. "
                                    "Focus on main dishes, side dishes, and accompaniments that contribute significant calories. "
                                    "Ignore garnishes, condiment packets, or tiny portions. "
                                    "If you cannot clearly identify any food items, respond with 'NO_FOOD_DETECTED'. "
                                    "If the image is too blurry, dark, or unclear, respond with 'IMAGE_UNCLEAR'. "
                                    "Format as: 'X portions/cups/grams of [specific food name]' "
                                    "Example: '1 cup steamed white rice, 120g roasted chicken thigh, 2 tablespoons stir-fried vegetables'"
                                )
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=400,
                temperature=0.2
            )
            
            if not response.choices or not response.choices[0].message.content:
                return {
                    'success': False,
                    'description': '',
                    'confidence': 'low',
                    'error': 'No response from AI'
                }
            
            food_description = response.choices[0].message.content.strip()
            logger.info(f"OpenAI Vision analysis: {food_description}")
            
            # Check for edge cases
            if food_description in ['NO_FOOD_DETECTED', 'IMAGE_UNCLEAR']:
                return {
                    'success': False,
                    'description': '',
                    'confidence': 'low',
                    'error': food_description
                }
            
            # Validate food detection quality (more lenient now)
            confidence = self._assess_food_description_quality(food_description)
            
            # Only reject if REALLY bad (was very_low, now only if no food words at all)
            if len(food_description.strip()) < 5:
                return {
                    'success': False,
                    'description': food_description,
                    'confidence': confidence,
                    'error': 'Food detection confidence too low'
                }
            
            return {
                'success': True,
                'description': food_description,
                'confidence': confidence,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Error analyzing food image: {e}")
            return {
                'success': False,
                'description': '',
                'confidence': 'low',
                'error': f"Failed to analyze food image: {str(e)}"
            }
    
    async def analyze_food_text(self, text_description: str) -> Dict[str, any]:
        """
        Analyze a text description of food using OpenAI.
        
        Args:
            text_description: User's text description of their meal
            
        Returns:
            Dictionary with 'success', 'description', 'confidence', and 'error' keys
        """
        try:
            # Check if text is too vague or unclear
            if len(text_description.strip()) < 3:
                return {
                    'success': False,
                    'description': '',
                    'confidence': 'low',
                    'error': 'Text description too short'
                }
            
            # Check for non-food related text (only very obvious cases)
            non_food_keywords = ['hello', 'hi there', 'testing', 'test message', 'just testing']
            if any(keyword == text_description.lower().strip() for keyword in non_food_keywords):
                return {
                    'success': False,
                    'description': '',
                    'confidence': 'low',
                    'error': 'Non-food text detected'
                }
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a nutrition expert. Convert user meal descriptions into realistic, "
                            "standardized food descriptions for nutritional lookup. "
                            "Estimate portions conservatively based on typical serving sizes. "
                            "For common dishes like 'chicken rice', break down into components with realistic portions. "
                            "Use specific cooking methods and standard measurements. "
                            "If the text doesn't describe any actual food, respond with 'NO_FOOD_DESCRIBED'."
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Convert this meal description into a realistic food list with conservative portions: {text_description}\n\n"
                            "Break down combo dishes into components. "
                            "If this doesn't describe actual food, respond with 'NO_FOOD_DESCRIBED'. "
                            "Example: 'chicken rice' becomes '1 cup steamed white rice, 100g roasted chicken thigh'"
                        )
                    }
                ],
                max_tokens=350,
                temperature=0.2
            )
            
            if not response.choices or not response.choices[0].message.content:
                return {
                    'success': False,
                    'description': '',
                    'confidence': 'low',
                    'error': 'No response from AI'
                }
            
            food_description = response.choices[0].message.content.strip()
            logger.info(f"OpenAI text analysis: {food_description}")
            
            # Check for edge cases
            if food_description == 'NO_FOOD_DESCRIBED':
                return {
                    'success': False,
                    'description': '',
                    'confidence': 'low',
                    'error': 'NO_FOOD_DESCRIBED'
                }
            
            # Validate food description quality (more lenient now)
            confidence = self._assess_food_description_quality(food_description)
            
            # Only reject if REALLY bad (was very_low, now only if no food words at all)
            if len(food_description.strip()) < 5:
                return {
                    'success': False,
                    'description': food_description,
                    'confidence': confidence,
                    'error': 'Food description confidence too low'
                }
            
            return {
                'success': True,
                'description': food_description,
                'confidence': confidence,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Error analyzing food text: {e}")
            return {
                'success': False,
                'description': '',
                'confidence': 'low',
                'error': f"Failed to analyze food text: {str(e)}"
            }
    
    async def extract_food_items(self, description: str) -> list:
        """
        Extract individual food items from a description for separate nutritional lookup.
        
        Args:
            description: Food description text
            
        Returns:
            List of individual food items
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Extract individual food items from the description. "
                            "Return each item on a separate line with quantity and description. "
                            "Format: 'quantity unit food_name preparation_method'"
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Extract individual food items from: {description}"
                    }
                ],
                max_tokens=300,
                temperature=0.2
            )
            
            items_text = response.choices[0].message.content.strip()
            food_items = [item.strip() for item in items_text.split('\n') if item.strip()]
            
            logger.info(f"Extracted food items: {food_items}")
            return food_items
            
        except Exception as e:
            logger.error(f"Error extracting food items: {e}")
            return [description]
    
    def _assess_food_description_quality(self, description: str) -> str:
        """
        Assess the quality and confidence of food description.
        
        Args:
            description: Food description text
            
        Returns:
            Confidence level: 'high', 'medium', 'low', or 'very_low'
        """
        if not description or len(description.strip()) < 10:
            return 'very_low'
        
        # Count specific food indicators
        food_indicators = 0
        
        # Specific measurements or portions
        measurement_patterns = [
            r'\d+\s*(cup|cups|tablespoon|tablespoons|teaspoon|teaspoons|oz|ounce|ounces)',
            r'\d+\s*g\b',  # grams
            r'\d+\s*ml\b',  # milliliters
            r'\d+\s*(piece|pieces|slice|slices|serving|servings)',
            r'(small|medium|large|half|quarter)\s+\w+'
        ]
        
        for pattern in measurement_patterns:
            if re.search(pattern, description, re.IGNORECASE):
                food_indicators += 1
        
        # Common food words (expanded list)
        food_words = [
            'rice', 'chicken', 'beef', 'pork', 'fish', 'vegetables', 'salad', 'soup',
            'bread', 'pasta', 'noodles', 'egg', 'cheese', 'milk', 'fruit', 'meat',
            'beans', 'potato', 'tomato', 'carrot', 'broccoli', 'spinach', 'onion',
            'food', 'meal', 'eat', 'ate', 'lunch', 'dinner', 'breakfast', 'snack',
            'sandwich', 'burger', 'pizza', 'curry', 'fried', 'cook', 'cooked'
        ]
        
        food_word_count = sum(1 for word in food_words if word in description.lower())
        food_indicators += min(food_word_count, 5)  # Increased cap to be more lenient
        
        # Cooking methods
        cooking_methods = [
            'grilled', 'fried', 'baked', 'steamed', 'boiled', 'roasted', 'sauteed',
            'stir-fried', 'pan-fried', 'deep-fried', 'braised', 'poached'
        ]
        
        if any(method in description.lower() for method in cooking_methods):
            food_indicators += 1
        
        # Red flags (non-food indicators)
        red_flags = [
            'unclear', 'cannot', 'unable', 'not sure', 'maybe', 'possibly',
            'plate', 'bowl', 'utensil', 'table', 'background', 'decoration'
        ]
        
        red_flag_count = sum(1 for flag in red_flags if flag in description.lower())
        food_indicators -= red_flag_count * 2  # Penalize red flags heavily
        
        # Determine confidence level (much more lenient)
        if food_indicators >= 3:
            return 'high'
        elif food_indicators >= 1:
            return 'medium'
        elif len(description.strip()) > 5:  # Any description longer than 5 chars gets low confidence
            return 'low'
        else:
            return 'very_low'