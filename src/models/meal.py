from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, List

@dataclass
class NutritionData:
    """Nutritional information for a meal or food item."""
    calories: float = 0.0
    protein: float = 0.0
    carbs: float = 0.0
    fat: float = 0.0
    fiber: float = 0.0
    sugar: float = 0.0
    sodium: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for Firebase storage."""
        return {
            'calories': self.calories,
            'protein': self.protein,
            'carbs': self.carbs,
            'fat': self.fat,
            'fiber': self.fiber,
            'sugar': self.sugar,
            'sodium': self.sodium
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'NutritionData':
        """Create from dictionary."""
        return cls(
            calories=data.get('calories', 0.0),
            protein=data.get('protein', 0.0),
            carbs=data.get('carbs', 0.0),
            fat=data.get('fat', 0.0),
            fiber=data.get('fiber', 0.0),
            sugar=data.get('sugar', 0.0),
            sodium=data.get('sodium', 0.0)
        )
    
    def multiply(self, factor: float) -> 'NutritionData':
        """Multiply all nutrition values by a factor."""
        return NutritionData(
            calories=self.calories * factor,
            protein=self.protein * factor,
            carbs=self.carbs * factor,
            fat=self.fat * factor,
            fiber=self.fiber * factor,
            sugar=self.sugar * factor,
            sodium=self.sodium * factor
        )

@dataclass
class FoodItem:
    """Individual food item within a meal."""
    name: str
    quantity: str
    nutrition: NutritionData
    confidence: str = 'medium'
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for Firebase storage."""
        return {
            'name': self.name,
            'quantity': self.quantity,
            'nutrition': self.nutrition.to_dict(),
            'confidence': self.confidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'FoodItem':
        """Create from dictionary."""
        return cls(
            name=data.get('name', ''),
            quantity=data.get('quantity', ''),
            nutrition=NutritionData.from_dict(data.get('nutrition', {})),
            confidence=data.get('confidence', 'medium')
        )

@dataclass
class Meal:
    """Complete meal with all food items and metadata."""
    id: Optional[str] = None
    user_id: str = ''
    timestamp: datetime = None
    input_type: str = 'text'  # 'text' or 'photo'
    input_value: str = ''
    food_description: str = ''
    food_items: List[FoodItem] = None
    nutrition: NutritionData = None
    confidence: str = 'medium'
    
    def __post_init__(self):
        """Initialize defaults after creation."""
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.food_items is None:
            self.food_items = []
        if self.nutrition is None:
            self.nutrition = NutritionData()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for Firebase storage."""
        return {
            'user_id': self.user_id,
            'timestamp': self.timestamp,
            'input_type': self.input_type,
            'input_value': self.input_value,
            'food_description': self.food_description,
            'food_items': [item.to_dict() for item in self.food_items],
            'nutrition': self.nutrition.to_dict(),
            'confidence': self.confidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict, meal_id: Optional[str] = None) -> 'Meal':
        """Create from dictionary."""
        return cls(
            id=meal_id,
            user_id=data.get('user_id', ''),
            timestamp=data.get('timestamp', datetime.now()),
            input_type=data.get('input_type', 'text'),
            input_value=data.get('input_value', ''),
            food_description=data.get('food_description', ''),
            food_items=[FoodItem.from_dict(item) for item in data.get('food_items', [])],
            nutrition=NutritionData.from_dict(data.get('nutrition', {})),
            confidence=data.get('confidence', 'medium')
        )
    
    def add_food_item(self, food_item: FoodItem):
        """Add a food item to the meal."""
        self.food_items.append(food_item)
        self._recalculate_nutrition()
    
    def remove_food_item(self, index: int):
        """Remove a food item by index."""
        if 0 <= index < len(self.food_items):
            self.food_items.pop(index)
            self._recalculate_nutrition()
    
    def update_food_item(self, index: int, updated_item: FoodItem):
        """Update a food item by index."""
        if 0 <= index < len(self.food_items):
            self.food_items[index] = updated_item
            self._recalculate_nutrition()
    
    def _recalculate_nutrition(self):
        """Recalculate total nutrition from all food items."""
        if not self.food_items:
            self.nutrition = NutritionData()
            return
        
        total_nutrition = NutritionData()
        for item in self.food_items:
            total_nutrition.calories += item.nutrition.calories
            total_nutrition.protein += item.nutrition.protein
            total_nutrition.carbs += item.nutrition.carbs
            total_nutrition.fat += item.nutrition.fat
            total_nutrition.fiber += item.nutrition.fiber
            total_nutrition.sugar += item.nutrition.sugar
            total_nutrition.sodium += item.nutrition.sodium
        
        self.nutrition = total_nutrition

@dataclass
class DailySummary:
    """Daily nutrition summary for a user."""
    user_id: str
    date: str
    total_calories: float = 0.0
    total_protein: float = 0.0
    total_carbs: float = 0.0
    total_fat: float = 0.0
    total_fiber: float = 0.0
    total_sugar: float = 0.0
    total_sodium: float = 0.0
    meal_count: int = 0
    created_at: datetime = None
    last_updated: datetime = None
    
    def __post_init__(self):
        """Initialize defaults after creation."""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.last_updated is None:
            self.last_updated = datetime.now()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for Firebase storage."""
        return {
            'user_id': self.user_id,
            'date': self.date,
            'total_calories': self.total_calories,
            'total_protein': self.total_protein,
            'total_carbs': self.total_carbs,
            'total_fat': self.total_fat,
            'total_fiber': self.total_fiber,
            'total_sugar': self.total_sugar,
            'total_sodium': self.total_sodium,
            'meal_count': self.meal_count,
            'created_at': self.created_at,
            'last_updated': self.last_updated
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'DailySummary':
        """Create from dictionary."""
        return cls(
            user_id=data.get('user_id', ''),
            date=data.get('date', ''),
            total_calories=data.get('total_calories', 0.0),
            total_protein=data.get('total_protein', 0.0),
            total_carbs=data.get('total_carbs', 0.0),
            total_fat=data.get('total_fat', 0.0),
            total_fiber=data.get('total_fiber', 0.0),
            total_sugar=data.get('total_sugar', 0.0),
            total_sodium=data.get('total_sodium', 0.0),
            meal_count=data.get('meal_count', 0),
            created_at=data.get('created_at', datetime.now()),
            last_updated=data.get('last_updated', datetime.now())
        )
    
    def add_meal(self, meal: Meal):
        """Add a meal to the daily summary."""
        self.total_calories += meal.nutrition.calories
        self.total_protein += meal.nutrition.protein
        self.total_carbs += meal.nutrition.carbs
        self.total_fat += meal.nutrition.fat
        self.total_fiber += meal.nutrition.fiber
        self.total_sugar += meal.nutrition.sugar
        self.total_sodium += meal.nutrition.sodium
        self.meal_count += 1
        self.last_updated = datetime.now()
    
    def subtract_meal(self, meal: Meal):
        """Subtract a meal from the daily summary."""
        self.total_calories -= meal.nutrition.calories
        self.total_protein -= meal.nutrition.protein
        self.total_carbs -= meal.nutrition.carbs
        self.total_fat -= meal.nutrition.fat
        self.total_fiber -= meal.nutrition.fiber
        self.total_sugar -= meal.nutrition.sugar
        self.total_sodium -= meal.nutrition.sodium
        self.meal_count = max(0, self.meal_count - 1)
        self.last_updated = datetime.now()