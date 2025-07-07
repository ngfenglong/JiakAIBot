from typing import Dict, List
from datetime import datetime
from ..models.meal import Meal, NutritionData, DailySummary

def format_nutrition_display(nutrition: NutritionData, show_detailed: bool = False) -> str:
    """
    Format nutrition data for display.
    
    Args:
        nutrition: NutritionData object
        show_detailed: Whether to show detailed nutrition info
        
    Returns:
        Formatted nutrition string
    """
    basic_info = (
        f"🔥 {nutrition.calories:.0f} cal | "
        f"🥩 {nutrition.protein:.1f}g | "
        f"🍞 {nutrition.carbs:.1f}g | "
        f"🥑 {nutrition.fat:.1f}g"
    )
    
    if not show_detailed:
        return basic_info
    
    detailed_info = (
        f"{basic_info}\n"
        f"🌾 Fiber: {nutrition.fiber:.1f}g | "
        f"🍯 Sugar: {nutrition.sugar:.1f}g | "
        f"🧂 Sodium: {nutrition.sodium:.0f}mg"
    )
    
    return detailed_info

def format_meal_display(meal: Meal, show_time: bool = True, show_detailed: bool = False) -> str:
    """
    Format meal for display.
    
    Args:
        meal: Meal object
        show_time: Whether to show timestamp
        show_detailed: Whether to show detailed nutrition
        
    Returns:
        Formatted meal string
    """
    time_str = ""
    if show_time:
        time_str = f"[{meal.timestamp.strftime('%H:%M')}] "
    
    confidence_icon = {
        'high': '🎯',
        'medium': '🔍',
        'low': '❓',
        'very_low': '⚠️'
    }.get(meal.confidence, '🔍')
    
    return (
        f"{time_str}{meal.food_description} {confidence_icon}\n"
        f"   {format_nutrition_display(meal.nutrition, show_detailed)}"
    )

def format_daily_summary_display(summary: DailySummary) -> str:
    """
    Format daily summary for display.
    
    Args:
        summary: DailySummary object
        
    Returns:
        Formatted summary string
    """
    return (
        f"📊 Summary for {summary.date}\n\n"
        f"🔥 Calories: {summary.total_calories:.0f}\n"
        f"🥩 Protein: {summary.total_protein:.1f}g\n"
        f"🍞 Carbs: {summary.total_carbs:.1f}g\n"
        f"🥑 Fat: {summary.total_fat:.1f}g\n"
        f"🍽️ Meals: {summary.meal_count}"
    )

def format_weekly_stats_display(stats: Dict) -> str:
    """
    Format weekly statistics for display.
    
    Args:
        stats: Statistics dictionary
        
    Returns:
        Formatted stats string
    """
    return (
        f"📊 Weekly Stats (Last {stats.get('period_days', 7)} days)\n\n"
        f"📅 Active Days: {stats.get('active_days', 0)}/{stats.get('period_days', 7)}\n"
        f"🔥 Total Calories: {stats.get('total_calories', 0):.0f}\n"
        f"🍽️ Total Meals: {stats.get('total_meals', 0)}\n"
        f"📈 Avg Calories/Day: {stats.get('avg_calories_per_day', 0):.0f}\n"
        f"🥘 Avg Meals/Day: {stats.get('avg_meals_per_day', 0):.1f}"
    )

def format_trend_display(trend_data: List[Dict]) -> str:
    """
    Format trend data for display.
    
    Args:
        trend_data: List of daily trend data
        
    Returns:
        Formatted trend string
    """
    if not trend_data:
        return "📈 No trend data available"
    
    result = "📈 Calorie Trends (Last 7 Days)\n\n"
    
    for day_data in trend_data:
        date = day_data.get('date', '')
        calories = day_data.get('calories', 0)
        meals = day_data.get('meals', 0)
        
        # Create simple bar chart
        bar_length = min(int(calories / 100), 20)
        bar = "█" * bar_length
        
        result += f"{date}: {calories:.0f} cal ({meals} meals)\n{bar}\n\n"
    
    return result

def format_confidence_warning(confidence: str) -> str:
    """
    Format confidence warning message.
    
    Args:
        confidence: Confidence level string
        
    Returns:
        Warning message or empty string
    """
    warnings = {
        'very_low': "⚠️ Very low confidence - please verify nutrition values",
        'low': "❓ Low confidence - please review nutrition values"
    }
    
    return warnings.get(confidence, "")

def format_calorie_warning(calories: float) -> str:
    """
    Format calorie warning message.
    
    Args:
        calories: Calorie count
        
    Returns:
        Warning message or empty string
    """
    if calories > 1000:
        return "⚠️ This seems like a high calorie estimate. Please review and adjust if needed."
    elif calories < 50:
        return "⚠️ This seems like a low calorie estimate. Please review and adjust if needed."
    return ""

def format_meal_list_display(meals: List[Meal], show_date: bool = False) -> str:
    """
    Format a list of meals for display.
    
    Args:
        meals: List of Meal objects
        show_date: Whether to show dates
        
    Returns:
        Formatted meal list string
    """
    if not meals:
        return "🍽️ No meals found"
    
    result = ""
    for i, meal in enumerate(meals, 1):
        date_str = ""
        if show_date:
            date_str = f"{meal.timestamp.strftime('%m-%d')} "
        
        result += f"{i}. {date_str}{format_meal_display(meal, show_time=True, show_detailed=False)}\n\n"
    
    return result.strip()

def truncate_text(text: str, max_length: int = 100) -> str:
    """
    Truncate text to maximum length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - 3] + "..."