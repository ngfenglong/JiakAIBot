import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from ..models.meal import NutritionData, FoodItem

def validate_nutrition_data(nutrition: Dict) -> Tuple[bool, str]:
    """
    Validate nutrition data dictionary.
    
    Args:
        nutrition: Nutrition data dictionary
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    required_fields = ['calories', 'protein', 'carbs', 'fat']
    
    for field in required_fields:
        if field not in nutrition:
            return False, f"Missing required field: {field}"
        
        try:
            value = float(nutrition[field])
            if value < 0:
                return False, f"Negative value not allowed for {field}"
            if value > 10000:  # Reasonable upper limit
                return False, f"Value too high for {field}: {value}"
        except (ValueError, TypeError):
            return False, f"Invalid numeric value for {field}"
    
    return True, ""

def validate_food_description(description: str) -> Tuple[bool, str]:
    """
    Validate food description.
    
    Args:
        description: Food description string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not description or not description.strip():
        return False, "Food description cannot be empty"
    
    if len(description.strip()) < 3:
        return False, "Food description too short"
    
    if len(description) > 500:
        return False, "Food description too long"
    
    # Check for common non-food phrases
    non_food_patterns = [
        r'\b(hello|hi|hey|thanks|thank you)\b',
        r'\b(how are you|what\'s up)\b',
        r'\b(test|testing)\b',
        r'\b(menu|help|command)\b'
    ]
    
    description_lower = description.lower()
    for pattern in non_food_patterns:
        if re.search(pattern, description_lower):
            return False, "Description doesn't appear to be food-related"
    
    return True, ""

def validate_user_id(user_id: str) -> Tuple[bool, str]:
    """
    Validate user ID.
    
    Args:
        user_id: User ID string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not user_id or not user_id.strip():
        return False, "User ID cannot be empty"
    
    if not re.match(r'^[0-9]+$', user_id):
        return False, "User ID must contain only numbers"
    
    return True, ""

def validate_date_string(date_str: str) -> Tuple[bool, str]:
    """
    Validate date string in YYYY-MM-DD format.
    
    Args:
        date_str: Date string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not date_str:
        return False, "Date string cannot be empty"
    
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True, ""
    except ValueError:
        return False, "Invalid date format. Use YYYY-MM-DD"

def validate_portion_multiplier(multiplier: float) -> Tuple[bool, str]:
    """
    Validate portion multiplier.
    
    Args:
        multiplier: Portion multiplier
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if multiplier <= 0:
        return False, "Portion multiplier must be positive"
    
    if multiplier > 10:
        return False, "Portion multiplier too large"
    
    return True, ""

def validate_food_item(food_item: FoodItem) -> Tuple[bool, str]:
    """
    Validate food item.
    
    Args:
        food_item: FoodItem object
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not food_item.name or not food_item.name.strip():
        return False, "Food item name cannot be empty"
    
    if len(food_item.name) > 200:
        return False, "Food item name too long"
    
    if not food_item.quantity or not food_item.quantity.strip():
        return False, "Food item quantity cannot be empty"
    
    is_valid, error = validate_nutrition_data(food_item.nutrition.to_dict())
    if not is_valid:
        return False, f"Invalid nutrition data: {error}"
    
    valid_confidence_levels = ['high', 'medium', 'low', 'very_low']
    if food_item.confidence not in valid_confidence_levels:
        return False, f"Invalid confidence level: {food_item.confidence}"
    
    return True, ""

def sanitize_text_input(text: str) -> str:
    """
    Sanitize text input.
    
    Args:
        text: Input text
        
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Remove potentially harmful characters
    text = re.sub(r'[<>"\']', '', text)
    
    return text

def validate_meal_edit_request(meal_id: str, edit_data: Dict) -> Tuple[bool, str]:
    """
    Validate meal edit request.
    
    Args:
        meal_id: Meal ID
        edit_data: Edit data dictionary
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not meal_id or not meal_id.strip():
        return False, "Meal ID cannot be empty"
    
    if not edit_data:
        return False, "Edit data cannot be empty"
    
    # Validate specific edit operations
    if 'food_items' in edit_data:
        food_items = edit_data['food_items']
        if not isinstance(food_items, list):
            return False, "Food items must be a list"
        
        for i, item_data in enumerate(food_items):
            if not isinstance(item_data, dict):
                return False, f"Food item {i} must be a dictionary"
            
            try:
                food_item = FoodItem.from_dict(item_data)
                is_valid, error = validate_food_item(food_item)
                if not is_valid:
                    return False, f"Food item {i}: {error}"
            except Exception as e:
                return False, f"Invalid food item {i}: {str(e)}"
    
    return True, ""

def is_reasonable_nutrition_values(nutrition: NutritionData) -> bool:
    """
    Check if nutrition values are reasonable.
    
    Args:
        nutrition: NutritionData object
        
    Returns:
        True if values seem reasonable
    """
    # Basic sanity checks
    if nutrition.calories < 0 or nutrition.calories > 5000:
        return False
    
    if nutrition.protein < 0 or nutrition.protein > 300:
        return False
    
    if nutrition.carbs < 0 or nutrition.carbs > 1000:
        return False
    
    if nutrition.fat < 0 or nutrition.fat > 500:
        return False
    
    # Check if macros add up reasonably to calories
    # 1g protein = 4 cal, 1g carbs = 4 cal, 1g fat = 9 cal
    calculated_calories = (nutrition.protein * 4) + (nutrition.carbs * 4) + (nutrition.fat * 9)
    
    if nutrition.calories > 0:
        ratio = calculated_calories / nutrition.calories
        if ratio < 0.5 or ratio > 2.0:  # Allow some variance
            return False
    
    return True