import os
import logging
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

from src.services.openai_service import OpenAIService
from src.services.nutritionix_service import NutritionixService
from src.services.firebase_service import FirebaseService
from src.models.meal import Meal, FoodItem, NutritionData
from src.utils.formatting import format_trend_display, format_meal_list_display
from src.utils.validation import validate_nutrition_data
from src.utils.middleware import require_access, require_access_callback, handle_access_request, check_message_access
import src.utils.access_control as access_control_module

load_dotenv()

# Debug: Print working directory and environment variables
print(f"Working directory: {os.getcwd()}")
print(f"AUTHORIZED_TELEGRAM_IDS from env: '{os.getenv('AUTHORIZED_TELEGRAM_IDS', 'NOT_SET')}'")
print(f"TELEGRAM_BOT_TOKEN exists: {bool(os.getenv('TELEGRAM_BOT_TOKEN'))}")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO'))
)
logger = logging.getLogger(__name__)

class JiakAI:
    def __init__(self):
        self.openai_service = OpenAIService()
        self.nutritionix_service = NutritionixService()
        self.firebase_service = FirebaseService()
        
        # Initialize global access control with firebase service
        access_control_module.access_control = access_control_module.AccessControl(self.firebase_service)
        
    @require_access
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /start is issued."""
        if not update.effective_user or not update.message:
            return
        
        user_id = str(update.effective_user.id)
        
        await self.firebase_service.create_user_if_not_exists(user_id)
        
        welcome_message = (
            "🍽️ Welcome to JiakAI! I'm your personal food tracking assistant.\n\n"
            "✨ How to log your meals:\n"
            "📸 Send a photo of your food\n"
            "💬 Describe what you ate (e.g., 'chicken rice', 'pasta with sauce')\n\n"
            "🎯 I can recognize most foods and dishes!\n"
            "📊 Use /summary for today's nutrition\n"
            "📝 Use /history to view past meals\n"
            "❓ Use /help for more information\n\n"
            "🚀 Ready to start tracking? Send me your first meal!"
        )
        
        await update.message.reply_text(welcome_message)
    
    @require_access
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /help is issued."""
        if not update.message:
            return
        
        help_text = (
            "🤖 JiakAI Commands:\n\n"
            "/start - Initialize the bot\n"
            "/summary - Get today's nutrition summary\n"
            "/history - View your meal history\n"
            "/help - Show this help message\n\n"
            "📸 Send a photo of your meal for analysis\n"
            "💬 Or describe your meal in text"
        )
        await update.message.reply_text(help_text)
    
    async def request_access_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /request_access command."""
        if not update.effective_user or not update.message:
            return
        
        user = update.effective_user
        user_id = str(user.id)
        
        # Check if user is already authorized
        from src.utils.access_control import check_user_access, log_access_request
        if check_user_access(user_id):
            await update.message.reply_text(
                "✅ You already have access to JiakAI!\n"
                "You can use all bot commands now. Try /start to begin."
            )
            return
        
        # Log the access request
        success = log_access_request(
            user_id, 
            user.username, 
            user.first_name, 
            user.last_name
        )
        
        if success:
            message = (
                "✅ **Access Request Submitted**\n\n"
                "Your request has been logged and will be reviewed by the administrators.\n\n"
                "**What happens next?**\n"
                "• Your request is now in the review queue\n"
                "• You'll be notified if your access is approved\n"
                "• Please be patient as reviews may take some time\n\n"
                "**Information Collected:**\n"
                f"• Telegram ID: `{user_id}`\n"
                f"• Username: @{user.username if user.username else 'N/A'}\n"
                f"• Name: {user.first_name or ''} {user.last_name or ''}".strip()
            )
        else:
            message = (
                "ℹ️ **Request Already Exists**\n\n"
                "You have already submitted an access request.\n"
                "Please wait for administrator review.\n\n"
                "If you believe this is an error, please contact the administrator directly."
            )
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo messages."""
        if not update.effective_user or not update.message or not update.message.photo:
            return
        
        # Check access before processing
        if not check_message_access(update):
            from src.utils.middleware import send_access_denied_message
            await send_access_denied_message(update, context, update.effective_user)
            return
        
        user_id = str(update.effective_user.id)
        
        try:
            await update.message.reply_text("📸 Analyzing your meal photo...")
            
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            file_path = f"temp_{photo.file_id}.jpg"
            await file.download_to_drive(file_path)
            
            analysis_result = await self.openai_service.analyze_food_image(file_path)
            
            os.remove(file_path)
            
            # Handle edge cases - no food detected or analysis failed
            if not analysis_result['success']:
                await self._handle_analysis_failure(update, analysis_result)
                return
            
            food_description = analysis_result['description']
            confidence = analysis_result['confidence']
            
            nutrition_data = await self.nutritionix_service.get_nutrition_data(food_description)
            
            # Store pending meal data in context for confirmation
            pending_meal = {
                'timestamp': datetime.now(),
                'input_type': 'photo',
                'input_value': photo.file_id,
                'food_description': food_description,
                'nutrition': nutrition_data,
                'user_id': user_id,
                'confidence': confidence
            }
            
            # Store in context user_data for callback
            if 'pending_meals' not in context.user_data:
                context.user_data['pending_meals'] = {}
            
            # Use shorter meal_id to avoid Telegram callback data limit (64 bytes)
            meal_id = f"p_{hash(photo.file_id) % 100000}"
            context.user_data['pending_meals'][meal_id] = pending_meal
            
            # Create confirmation buttons
            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirm & Save", callback_data=f"confirm_{meal_id}"),
                    InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{meal_id}")
                ],
                [
                    InlineKeyboardButton("🔧 Adjust Portions", callback_data=f"adjust_{meal_id}"),
                    InlineKeyboardButton("✏️ Edit Items", callback_data=f"edit_{meal_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            response = self._format_confirmation_response(food_description, nutrition_data, confidence)
            await update.message.reply_text(response, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error processing photo: {e}")
            await update.message.reply_text("❌ Sorry, I had trouble analyzing your photo. Please try again.")
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages."""
        if not update.effective_user or not update.message or not update.message.text:
            return
        
        # Check access before processing
        if not check_message_access(update):
            from src.utils.middleware import send_access_denied_message
            await send_access_denied_message(update, context, update.effective_user)
            return
        
        user_id = str(update.effective_user.id)
        text = update.message.text
        
        try:
            await update.message.reply_text("💬 Analyzing your meal description...")
            
            analysis_result = await self.openai_service.analyze_food_text(text)
            
            # Handle edge cases - no food detected or analysis failed
            if not analysis_result['success']:
                await self._handle_analysis_failure(update, analysis_result)
                return
            
            food_description = analysis_result['description']
            confidence = analysis_result['confidence']
            
            nutrition_data = await self.nutritionix_service.get_nutrition_data(food_description)
            
            # Store pending meal data in context for confirmation
            pending_meal = {
                'timestamp': datetime.now(),
                'input_type': 'text',
                'input_value': text,
                'food_description': food_description,
                'nutrition': nutrition_data,
                'user_id': user_id,
                'confidence': confidence
            }
            
            # Store in context user_data for callback
            if 'pending_meals' not in context.user_data:
                context.user_data['pending_meals'] = {}
            
            # Use shorter meal_id to avoid Telegram callback data limit (64 bytes)
            meal_id = f"t_{hash(text) % 100000}"
            context.user_data['pending_meals'][meal_id] = pending_meal
            
            # Create confirmation buttons
            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirm & Save", callback_data=f"confirm_{meal_id}"),
                    InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{meal_id}")
                ],
                [
                    InlineKeyboardButton("🔧 Adjust Portions", callback_data=f"adjust_{meal_id}"),
                    InlineKeyboardButton("✏️ Edit Items", callback_data=f"edit_{meal_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            response = self._format_confirmation_response(food_description, nutrition_data, confidence)
            await update.message.reply_text(response, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error processing text: {e}")
            await update.message.reply_text("❌ Sorry, I had trouble analyzing your meal description. Please try again.")
    
    @require_access
    async def summary_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get daily nutrition summary."""
        if not update.effective_user or not update.message:
            return
        
        user_id = str(update.effective_user.id)
        
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            summary = await self.firebase_service.get_daily_summary(user_id, today)
            
            if not summary:
                await update.message.reply_text("📊 No meals logged for today yet!")
                return
            
            response = (
                f"📊 Today's Nutrition Summary ({today})\n\n"
                f"🔥 Calories: {summary.get('total_calories', 0):.0f}\n"
                f"🥩 Protein: {summary.get('total_protein', 0):.1f}g\n"
                f"🍞 Carbs: {summary.get('total_carbs', 0):.1f}g\n"
                f"🥑 Fat: {summary.get('total_fat', 0):.1f}g\n"
                f"🍽️ Meals: {summary.get('meal_count', 0)}"
            )
            
            await update.message.reply_text(response)
            
        except Exception as e:
            logger.error(f"Error getting summary: {e}")
            await update.message.reply_text("❌ Sorry, I had trouble getting your summary. Please try again.")
    
    @require_access
    async def history_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get meal history with date selection."""
        if not update.effective_user or not update.message:
            return
        
        # Create date selection buttons
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)
        
        keyboard = [
            [
                InlineKeyboardButton(f"📅 Today ({today.strftime('%m-%d')})", callback_data=f"history_{today.strftime('%Y-%m-%d')}"),
                InlineKeyboardButton(f"📅 Yesterday ({yesterday.strftime('%m-%d')})", callback_data=f"history_{yesterday.strftime('%Y-%m-%d')}")
            ],
            [
                InlineKeyboardButton(f"📅 {two_days_ago.strftime('%m-%d')}", callback_data=f"history_{two_days_ago.strftime('%Y-%m-%d')}"),
                InlineKeyboardButton("📊 Weekly Stats", callback_data="stats_week")
            ],
            [
                InlineKeyboardButton("🗑️ Delete Meal", callback_data="delete_meal"),
                InlineKeyboardButton("📈 View Trends", callback_data="trends")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📝 Select a date to view your meal history:",
            reply_markup=reply_markup
        )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks."""
        if not update.callback_query:
            return
        
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        # Handle access request before checking authorization for other callbacks
        if data == 'request_access':
            await handle_access_request(update, context)
            return
        
        # Check access for all other callbacks
        if not check_message_access(update):
            await query.answer("❌ Access denied. Please request access first.", show_alert=True)
            return
        
        if data.startswith('confirm_'):
            await self._handle_confirm_meal(query, context, data)
        elif data.startswith('cancel_'):
            await self._handle_cancel_meal(query, context, data)
        elif data.startswith('adjust_'):
            await self._handle_adjust_portions(query, context, data)
        elif data.startswith('portion_'):
            await self._handle_portion_change(query, context, data)
        elif data.startswith('back_'):
            await self._handle_back_to_confirmation(query, context, data)
        elif data.startswith('edit_'):
            await self._handle_edit_items(query, context, data)
        elif data.startswith('history_'):
            await self._handle_history_date(query, context, data)
        elif data == 'stats_week':
            await self._handle_weekly_stats(query, context)
        elif data == 'delete_meal':
            await self._handle_delete_meal_selection(query, context)
        elif data == 'trends':
            await self._handle_trends(query, context)
        elif data.startswith('edit_desc_'):
            await self._handle_edit_description(query, context, data)
        elif data.startswith('edit_cal_'):
            await self._handle_edit_calories(query, context, data)
        elif data.startswith('edit_prot_'):
            await self._handle_edit_protein(query, context, data)
        elif data.startswith('edit_carbs_'):
            await self._handle_edit_carbs(query, context, data)
        elif data.startswith('edit_fat_'):
            await self._handle_edit_fat(query, context, data)
        elif data.startswith('delete_confirm_'):
            await self._handle_delete_confirm(query, context, data)
        elif data == 'cancel_delete':
            await self._handle_cancel_delete(query, context)
        elif data.startswith('trend_'):
            await self._handle_trend_period(query, context, data)
        elif data == 'back_to_history':
            await self._handle_back_to_history(query, context)
        elif data.startswith('cal_adjust_'):
            await self._handle_nutrition_adjust(query, context, data, 'calories')
        elif data.startswith('prot_adjust_'):
            await self._handle_nutrition_adjust(query, context, data, 'protein')
        elif data.startswith('carbs_adjust_'):
            await self._handle_nutrition_adjust(query, context, data, 'carbs')
        elif data.startswith('fat_adjust_'):
            await self._handle_nutrition_adjust(query, context, data, 'fat')
    
    async def _handle_confirm_meal(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Confirm and save the meal."""
        meal_id = data.replace('confirm_', '')
        
        if 'pending_meals' not in context.user_data or meal_id not in context.user_data['pending_meals']:
            await query.edit_message_text("❌ Meal data not found. Please try again.")
            return
        
        meal_data = context.user_data['pending_meals'][meal_id]
        user_id = meal_data['user_id']
        
        # Save to Firebase
        saved_meal_id = await self.firebase_service.save_meal(user_id, meal_data)
        
        if saved_meal_id:
            response = (
                "✅ Meal saved successfully!\n\n"
                f"🍽️ {meal_data['food_description']}\n"
                f"🔥 {meal_data['nutrition'].get('calories', 0):.0f} calories\n"
                f"🥩 {meal_data['nutrition'].get('protein', 0):.1f}g protein\n"
                f"🍞 {meal_data['nutrition'].get('carbs', 0):.1f}g carbs\n"
                f"🥑 {meal_data['nutrition'].get('fat', 0):.1f}g fat"
            )
            await query.edit_message_text(response)
            
            # Clean up pending meal
            del context.user_data['pending_meals'][meal_id]
        else:
            await query.edit_message_text("❌ Failed to save meal. Please try again.")
    
    async def _handle_cancel_meal(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Cancel the meal entry."""
        meal_id = data.replace('cancel_', '')
        
        if 'pending_meals' in context.user_data and meal_id in context.user_data['pending_meals']:
            del context.user_data['pending_meals'][meal_id]
        
        await query.edit_message_text("❌ Meal entry cancelled.")
    
    async def _handle_adjust_portions(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle portion adjustment."""
        meal_id = data.replace('adjust_', '')
        
        keyboard = [
            [
                InlineKeyboardButton("0.5x (Half)", callback_data=f"portion_{meal_id}_0.5"),
                InlineKeyboardButton("0.75x", callback_data=f"portion_{meal_id}_0.75")
            ],
            [
                InlineKeyboardButton("1.25x", callback_data=f"portion_{meal_id}_1.25"),
                InlineKeyboardButton("1.5x", callback_data=f"portion_{meal_id}_1.5")
            ],
            [
                InlineKeyboardButton("2x (Double)", callback_data=f"portion_{meal_id}_2.0"),
                InlineKeyboardButton("🔙 Back", callback_data=f"back_{meal_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🔧 Adjust your portion size:",
            reply_markup=reply_markup
        )
    
    async def _handle_portion_change(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle portion size change."""
        parts = data.split('_')
        # For new format: portion_p_12345_1.5 or portion_t_12345_1.5
        if len(parts) >= 4:
            meal_id = '_'.join(parts[1:-1])  # Reconstruct meal_id (p_12345 or t_12345)
            multiplier = float(parts[-1])
        else:
            # Fallback for any edge cases
            meal_id = parts[1]
            multiplier = float(parts[2])
        
        if 'pending_meals' not in context.user_data or meal_id not in context.user_data['pending_meals']:
            await query.edit_message_text("❌ Meal data not found. Please try again.")
            return
        
        # Adjust nutrition values
        meal_data = context.user_data['pending_meals'][meal_id]
        nutrition = meal_data['nutrition'].copy()
        
        for key in ['calories', 'protein', 'carbs', 'fat', 'fiber', 'sugar', 'sodium']:
            if key in nutrition:
                nutrition[key] = nutrition[key] * multiplier
        
        meal_data['nutrition'] = nutrition
        
        # Update food description to show portion adjustment
        original_description = meal_data['food_description']
        if multiplier == 0.5:
            portion_text = " (Half portion)"
        elif multiplier == 0.75:
            portion_text = " (3/4 portion)"
        elif multiplier == 1.25:
            portion_text = " (Large portion)"
        elif multiplier == 1.5:
            portion_text = " (1.5x portion)"
        elif multiplier == 2.0:
            portion_text = " (Double portion)"
        else:
            portion_text = f" ({multiplier}x portion)"
        
        meal_data['food_description'] = original_description + portion_text
        
        # Show updated confirmation
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm & Save", callback_data=f"confirm_{meal_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{meal_id}")
            ],
            [
                InlineKeyboardButton("🔧 Adjust Again", callback_data=f"adjust_{meal_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        response = self._format_confirmation_response(
            meal_data['food_description'], 
            nutrition, 
            meal_data.get('confidence', 'medium')
        )
        await query.edit_message_text(response, reply_markup=reply_markup)
    
    async def _handle_back_to_confirmation(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle back to confirmation."""
        meal_id = data.replace('back_', '')
        
        if 'pending_meals' not in context.user_data or meal_id not in context.user_data['pending_meals']:
            await query.edit_message_text("❌ Meal data not found. Please try again.")
            return
        
        meal_data = context.user_data['pending_meals'][meal_id]
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm & Save", callback_data=f"confirm_{meal_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{meal_id}")
            ],
            [
                InlineKeyboardButton("🔧 Adjust Portions", callback_data=f"adjust_{meal_id}"),
                InlineKeyboardButton("✏️ Edit Items", callback_data=f"edit_{meal_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        response = self._format_confirmation_response(
            meal_data['food_description'], 
            meal_data['nutrition'], 
            meal_data.get('confidence', 'medium')
        )
        await query.edit_message_text(response, reply_markup=reply_markup)
    
    async def _handle_edit_items(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle item editing."""
        meal_id = data.replace('edit_', '')
        
        if 'pending_meals' not in context.user_data or meal_id not in context.user_data['pending_meals']:
            await query.edit_message_text("❌ Meal data not found. Please try again.")
            return
        
        meal_data = context.user_data['pending_meals'][meal_id]
        
        # Store the meal being edited
        context.user_data['editing_meal'] = meal_id
        
        # Show current items for editing
        nutrition = meal_data['nutrition']
        food_description = meal_data['food_description']
        
        # For now, show a simplified edit interface
        keyboard = [
            [
                InlineKeyboardButton("📝 Edit Description", callback_data=f"edit_desc_{meal_id}"),
                InlineKeyboardButton("🔢 Edit Calories", callback_data=f"edit_cal_{meal_id}")
            ],
            [
                InlineKeyboardButton("🥩 Edit Protein", callback_data=f"edit_prot_{meal_id}"),
                InlineKeyboardButton("🍞 Edit Carbs", callback_data=f"edit_carbs_{meal_id}")
            ],
            [
                InlineKeyboardButton("🥑 Edit Fat", callback_data=f"edit_fat_{meal_id}"),
                InlineKeyboardButton("🔙 Back", callback_data=f"back_{meal_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        response = (
            f"✏️ Edit Meal Items\n\n"
            f"🍽️ Current: {food_description}\n\n"
            f"📊 Current Nutrition:\n"
            f"🔥 Calories: {nutrition.get('calories', 0):.0f}\n"
            f"🥩 Protein: {nutrition.get('protein', 0):.1f}g\n"
            f"🍞 Carbs: {nutrition.get('carbs', 0):.1f}g\n"
            f"🥑 Fat: {nutrition.get('fat', 0):.1f}g\n\n"
            f"📝 Choose what to edit:"
        )
        
        await query.edit_message_text(response, reply_markup=reply_markup)
    
    async def _handle_history_date(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle history date selection."""
        date = data.replace('history_', '')
        user_id = str(query.from_user.id)
        
        try:
            meals = await self.firebase_service.get_meals_for_date(user_id, date)
            
            if not meals:
                await query.edit_message_text(f"📝 No meals logged for {date}")
                return
            
            response = f"📝 Meals for {date}\n\n"
            
            for i, meal in enumerate(meals, 1):
                nutrition = meal.get('nutrition', {})
                time_str = meal.get('timestamp', datetime.now()).strftime('%H:%M')
                response += (
                    f"{i}. [{time_str}] {meal.get('food_description', 'Unknown food')}\n"
                    f"   🔥 {nutrition.get('calories', 0):.0f} cal | "
                    f"🥩 {nutrition.get('protein', 0):.1f}g | "
                    f"🍞 {nutrition.get('carbs', 0):.1f}g | "
                    f"🥑 {nutrition.get('fat', 0):.1f}g\n\n"
                )
            
            await query.edit_message_text(response)
            
        except Exception as e:
            logger.error(f"Error getting history for {date}: {e}")
            await query.edit_message_text("❌ Sorry, I had trouble getting your history.")
    
    async def _handle_weekly_stats(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle weekly statistics."""
        user_id = str(query.from_user.id)
        
        try:
            stats = await self.firebase_service.get_user_stats(user_id, days=7)
            
            response = (
                f"📊 Weekly Stats (Last 7 days)\n\n"
                f"📅 Active Days: {stats.get('active_days', 0)}/7\n"
                f"🔥 Total Calories: {stats.get('total_calories', 0):.0f}\n"
                f"🍽️ Total Meals: {stats.get('total_meals', 0)}\n"
                f"📈 Avg Calories/Day: {stats.get('avg_calories_per_day', 0):.0f}\n"
                f"🥘 Avg Meals/Day: {stats.get('avg_meals_per_day', 0):.1f}"
            )
            
            await query.edit_message_text(response)
            
        except Exception as e:
            logger.error(f"Error getting weekly stats: {e}")
            await query.edit_message_text("❌ Sorry, I had trouble getting your stats.")
    
    async def _handle_delete_meal_selection(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle meal deletion selection."""
        user_id = str(query.from_user.id)
        
        try:
            # Get recent meals for deletion
            recent_meals = await self.firebase_service.get_recent_meals(user_id, limit=5)
            
            if not recent_meals:
                await query.edit_message_text("🗑️ No recent meals found to delete.")
                return
            
            # Create buttons for each meal
            keyboard = []
            for i, meal in enumerate(recent_meals):
                meal_id = meal.get('id')
                food_desc = meal.get('food_description', 'Unknown meal')
                time_str = meal.get('timestamp', datetime.now()).strftime('%m-%d %H:%M')
                
                # Truncate description if too long
                if len(food_desc) > 30:
                    food_desc = food_desc[:30] + "..."
                
                button_text = f"🗑️ [{time_str}] {food_desc}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delete_confirm_{meal_id}")])
            
            keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_delete")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "🗑️ Select a meal to delete:\n\n"
                "⚠️ This action cannot be undone!",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error in delete meal selection: {e}")
            await query.edit_message_text("❌ Error loading meals for deletion.")
    
    async def _handle_trends(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle trends display."""
        user_id = str(query.from_user.id)
        
        try:
            # Get trend data for the past 7 days
            trend_data = await self.firebase_service.get_trend_data(user_id, days=7)
            
            if not trend_data:
                await query.edit_message_text(
                    "📈 No trend data available yet.\n"
                    "Start logging meals to see your trends!"
                )
                return
            
            # Format the trend display
            response = format_trend_display(trend_data)
            
            # Add trend options
            keyboard = [
                [
                    InlineKeyboardButton("📊 7 Days", callback_data="trend_7"),
                    InlineKeyboardButton("📊 14 Days", callback_data="trend_14")
                ],
                [
                    InlineKeyboardButton("📊 30 Days", callback_data="trend_30"),
                    InlineKeyboardButton("🔙 Back", callback_data="back_to_history")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(response, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error getting trends: {e}")
            await query.edit_message_text("❌ Error loading trend data.")
    
    async def _handle_analysis_failure(self, update: Update, analysis_result: dict):
        """Handle failed food analysis with user-friendly messages."""
        error = analysis_result.get('error', 'Unknown error')
        
        if error == 'NO_FOOD_DETECTED':
            message = (
                "🤔 I couldn't detect any food in this image.\n\n"
                "💡 Tips for better results:\n"
                "• Make sure food is clearly visible\n"
                "• Avoid photos with only plates, utensils, or packaging\n"
                "• Try taking a closer photo of your meal\n"
                "• Ensure good lighting\n\n"
                "📝 You can also describe your meal in text instead!"
            )
        elif error == 'IMAGE_UNCLEAR':
            message = (
                "📸 The image is too unclear for me to analyze.\n\n"
                "💡 Tips for better photos:\n"
                "• Use good lighting (natural light works best)\n"
                "• Hold the camera steady\n"
                "• Get closer to your food\n"
                "• Avoid blurry or dark photos\n\n"
                "📝 You can also describe your meal in text instead!"
            )
        elif error == 'NO_FOOD_DESCRIBED':
            message = (
                "🤔 I couldn't identify any food from your description.\n\n"
                "💡 Try being more specific:\n"
                "• Include food names and quantities\n"
                "• Example: 'chicken rice' → '1 cup rice with grilled chicken'\n"
                "• Mention cooking methods if known\n\n"
                "📸 You can also send a photo of your meal!"
            )
        elif error == 'Non-food text detected':
            message = (
                "🤖 It looks like you sent a non-food message.\n\n"
                "📝 To log a meal, please:\n"
                "• Describe what you ate (e.g., 'sandwich and salad')\n"
                "• Send a photo of your food\n"
                "• Use commands like /summary or /history for other features"
            )
        elif error == 'Text description too short':
            message = (
                "📝 Your description is too short for me to understand.\n\n"
                "💡 Please provide more details:\n"
                "• What foods did you eat?\n"
                "• Approximate quantities if known\n"
                "• Example: 'pasta with meat sauce' or 'fruit salad'"
            )
        elif 'confidence too low' in error:
            message = (
                "⚠️ I'm not confident about my analysis of this food.\n\n"
                "💡 For better accuracy:\n"
                "• Try a clearer photo with better lighting\n"
                "• Describe your meal in text with more details\n"
                "• Focus on the main food items"
            )
        else:
            message = (
                "❌ Sorry, I had trouble analyzing your input.\n\n"
                "💡 Please try:\n"
                "• Taking a clearer photo of your food\n"
                "• Describing your meal in text\n"
                "• Making sure there's actual food visible\n\n"
                f"Technical details: {error}"
            )
        
        await update.message.reply_text(message)
    
    def _format_nutrition_response(self, food_description: str, nutrition_data: dict) -> str:
        """Format nutrition data response."""
        return (
            f"🍽️ {food_description}\n\n"
            f"📊 Nutrition Information:\n"
            f"🔥 Calories: {nutrition_data.get('calories', 0):.0f}\n"
            f"🥩 Protein: {nutrition_data.get('protein', 0):.1f}g\n"
            f"🍞 Carbs: {nutrition_data.get('carbs', 0):.1f}g\n"
            f"🥑 Fat: {nutrition_data.get('fat', 0):.1f}g\n\n"
            f"✅ Meal logged successfully!"
        )
    
    def _format_confirmation_response(self, food_description: str, nutrition_data: dict, confidence: str = 'medium') -> str:
        """Format confirmation response with nutrition data and confidence."""
        calories = nutrition_data.get('calories', 0)
        
        # Add calorie warning if it seems too high
        warning = ""
        if calories > 1000:
            warning = "\n⚠️ This seems like a high calorie estimate. Please review and adjust if needed."
        elif calories < 50:
            warning = "\n⚠️ This seems like a low calorie estimate. Please review and adjust if needed."
        
        # Add confidence indicator
        confidence_icons = {
            'high': '🎯',
            'medium': '🔍', 
            'low': '❓',
            'very_low': '⚠️'
        }
        
        confidence_text = {
            'high': '(High confidence)',
            'medium': '(Medium confidence)',
            'low': '(Low confidence - please review)',
            'very_low': '(Very low confidence - please verify)'
        }
        
        confidence_icon = confidence_icons.get(confidence, '🔍')
        confidence_msg = confidence_text.get(confidence, '')
        
        return (
            f"🍽️ {food_description}\n\n"
            f"📊 Detected Nutrition: {confidence_icon} {confidence_msg}\n"
            f"🔥 Calories: {calories:.0f}\n"
            f"🥩 Protein: {nutrition_data.get('protein', 0):.1f}g\n"
            f"🍞 Carbs: {nutrition_data.get('carbs', 0):.1f}g\n"
            f"🥑 Fat: {nutrition_data.get('fat', 0):.1f}g{warning}\n\n"
            f"👆 Please confirm or adjust this meal:"
        )
    
    async def _handle_edit_description(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle editing meal description."""
        await query.edit_message_text(
            "✏️ Description editing requires text input.\n\n"
            "For now, please:\n"
            "1. Cancel this entry\n"
            "2. Create a new entry with the correct description\n"
            "3. Use the portion adjustment feature to modify quantities"
        )
    
    async def _handle_edit_calories(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle editing calories."""
        meal_id = data.replace('edit_cal_', '')
        
        # Create calorie adjustment buttons
        keyboard = [
            [
                InlineKeyboardButton("➖ 100 cal", callback_data=f"cal_adjust_{meal_id}_-100"),
                InlineKeyboardButton("➖ 50 cal", callback_data=f"cal_adjust_{meal_id}_-50")
            ],
            [
                InlineKeyboardButton("➕ 50 cal", callback_data=f"cal_adjust_{meal_id}_50"),
                InlineKeyboardButton("➕ 100 cal", callback_data=f"cal_adjust_{meal_id}_100")
            ],
            [
                InlineKeyboardButton("➕ 200 cal", callback_data=f"cal_adjust_{meal_id}_200"),
                InlineKeyboardButton("🔙 Back", callback_data=f"edit_{meal_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🔥 Adjust calories:\n\n"
            "Choose how much to add or subtract:",
            reply_markup=reply_markup
        )
    
    async def _handle_edit_protein(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle editing protein."""
        meal_id = data.replace('edit_prot_', '')
        
        # Create protein adjustment buttons
        keyboard = [
            [
                InlineKeyboardButton("➖ 10g", callback_data=f"prot_adjust_{meal_id}_-10"),
                InlineKeyboardButton("➖ 5g", callback_data=f"prot_adjust_{meal_id}_-5")
            ],
            [
                InlineKeyboardButton("➕ 5g", callback_data=f"prot_adjust_{meal_id}_5"),
                InlineKeyboardButton("➕ 10g", callback_data=f"prot_adjust_{meal_id}_10")
            ],
            [
                InlineKeyboardButton("➕ 20g", callback_data=f"prot_adjust_{meal_id}_20"),
                InlineKeyboardButton("🔙 Back", callback_data=f"edit_{meal_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🥩 Adjust protein:\n\n"
            "Choose how much to add or subtract:",
            reply_markup=reply_markup
        )
    
    async def _handle_edit_carbs(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle editing carbs."""
        meal_id = data.replace('edit_carbs_', '')
        
        # Create carbs adjustment buttons
        keyboard = [
            [
                InlineKeyboardButton("➖ 20g", callback_data=f"carbs_adjust_{meal_id}_-20"),
                InlineKeyboardButton("➖ 10g", callback_data=f"carbs_adjust_{meal_id}_-10")
            ],
            [
                InlineKeyboardButton("➕ 10g", callback_data=f"carbs_adjust_{meal_id}_10"),
                InlineKeyboardButton("➕ 20g", callback_data=f"carbs_adjust_{meal_id}_20")
            ],
            [
                InlineKeyboardButton("➕ 50g", callback_data=f"carbs_adjust_{meal_id}_50"),
                InlineKeyboardButton("🔙 Back", callback_data=f"edit_{meal_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🍞 Adjust carbs:\n\n"
            "Choose how much to add or subtract:",
            reply_markup=reply_markup
        )
    
    async def _handle_edit_fat(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle editing fat."""
        meal_id = data.replace('edit_fat_', '')
        
        # Create fat adjustment buttons
        keyboard = [
            [
                InlineKeyboardButton("➖ 10g", callback_data=f"fat_adjust_{meal_id}_-10"),
                InlineKeyboardButton("➖ 5g", callback_data=f"fat_adjust_{meal_id}_-5")
            ],
            [
                InlineKeyboardButton("➕ 5g", callback_data=f"fat_adjust_{meal_id}_5"),
                InlineKeyboardButton("➕ 10g", callback_data=f"fat_adjust_{meal_id}_10")
            ],
            [
                InlineKeyboardButton("➕ 20g", callback_data=f"fat_adjust_{meal_id}_20"),
                InlineKeyboardButton("🔙 Back", callback_data=f"edit_{meal_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🥑 Adjust fat:\n\n"
            "Choose how much to add or subtract:",
            reply_markup=reply_markup
        )
    
    async def _handle_delete_confirm(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle meal deletion confirmation."""
        meal_id = data.replace('delete_confirm_', '')
        user_id = str(query.from_user.id)
        
        try:
            # Get meal details first
            meal_data = await self.firebase_service.get_meal_by_id(user_id, meal_id)
            if not meal_data:
                await query.edit_message_text("❌ Meal not found.")
                return
            
            # Delete the meal
            success = await self.firebase_service.delete_meal(user_id, meal_id)
            
            if success:
                food_desc = meal_data.get('food_description', 'Unknown meal')
                await query.edit_message_text(
                    f"✅ Meal deleted successfully!\n\n"
                    f"🗑️ Deleted: {food_desc}\n"
                    f"📊 Daily summary has been updated."
                )
            else:
                await query.edit_message_text("❌ Failed to delete meal. Please try again.")
        
        except Exception as e:
            logger.error(f"Error deleting meal: {e}")
            await query.edit_message_text("❌ Error deleting meal.")
    
    async def _handle_cancel_delete(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle cancel delete operation."""
        await query.edit_message_text("❌ Delete operation cancelled.")
    
    async def _handle_trend_period(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle different trend periods."""
        user_id = str(query.from_user.id)
        period = data.replace('trend_', '')
        days = int(period)
        
        try:
            # Get trend data for the specified period
            trend_data = await self.firebase_service.get_trend_data(user_id, days=days)
            
            if not trend_data:
                await query.edit_message_text(
                    f"📈 No trend data available for the past {days} days.\n"
                    "Start logging meals to see your trends!"
                )
                return
            
            # Format the trend display
            response = format_trend_display(trend_data)
            response = response.replace("(Last 7 Days)", f"(Last {days} Days)")
            
            # Add trend options
            keyboard = [
                [
                    InlineKeyboardButton("📊 7 Days", callback_data="trend_7"),
                    InlineKeyboardButton("📊 14 Days", callback_data="trend_14")
                ],
                [
                    InlineKeyboardButton("📊 30 Days", callback_data="trend_30"),
                    InlineKeyboardButton("🔙 Back", callback_data="back_to_history")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(response, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error getting trends for {days} days: {e}")
            await query.edit_message_text("❌ Error loading trend data.")
    
    async def _handle_back_to_history(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle back to history menu."""
        # Recreate the history menu
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)
        
        keyboard = [
            [
                InlineKeyboardButton(f"📅 Today ({today.strftime('%m-%d')})", callback_data=f"history_{today.strftime('%Y-%m-%d')}"),
                InlineKeyboardButton(f"📅 Yesterday ({yesterday.strftime('%m-%d')})", callback_data=f"history_{yesterday.strftime('%Y-%m-%d')}")
            ],
            [
                InlineKeyboardButton(f"📅 {two_days_ago.strftime('%m-%d')}", callback_data=f"history_{two_days_ago.strftime('%Y-%m-%d')}"),
                InlineKeyboardButton("📊 Weekly Stats", callback_data="stats_week")
            ],
            [
                InlineKeyboardButton("🗑️ Delete Meal", callback_data="delete_meal"),
                InlineKeyboardButton("📈 View Trends", callback_data="trends")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📝 Select a date to view your meal history:",
            reply_markup=reply_markup
        )
    
    async def _handle_nutrition_adjust(self, query, context: ContextTypes.DEFAULT_TYPE, data: str, nutrient: str):
        """Handle nutrition value adjustment."""
        # Parse the adjustment data
        parts = data.split('_')
        meal_id = '_'.join(parts[2:-1])  # Reconstruct meal_id
        adjustment = float(parts[-1])
        
        if 'pending_meals' not in context.user_data or meal_id not in context.user_data['pending_meals']:
            await query.edit_message_text("❌ Meal data not found. Please try again.")
            return
        
        meal_data = context.user_data['pending_meals'][meal_id]
        nutrition = meal_data['nutrition'].copy()
        
        # Apply the adjustment
        if nutrient in nutrition:
            nutrition[nutrient] = max(0, nutrition[nutrient] + adjustment)
        
        meal_data['nutrition'] = nutrition
        
        # Show updated confirmation
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm & Save", callback_data=f"confirm_{meal_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{meal_id}")
            ],
            [
                InlineKeyboardButton("🔧 Adjust More", callback_data=f"edit_{meal_id}"),
                InlineKeyboardButton("🔙 Back", callback_data=f"back_{meal_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        response = self._format_confirmation_response(
            meal_data['food_description'], 
            nutrition, 
            meal_data.get('confidence', 'medium')
        )
        
        await query.edit_message_text(response, reply_markup=reply_markup)

async def setup_bot_menu(application):
    """Set up the bot menu commands."""
    commands = [
        BotCommand("start", "🚀 Start the bot"),
        BotCommand("summary", "📊 Today's nutrition summary"),
        BotCommand("history", "📝 View meal history"),
        BotCommand("help", "❓ Get help and instructions"),
        BotCommand("request_access", "🔑 Request access to use the bot"),
    ]
    
    await application.bot.set_my_commands(commands)
    logger.info("Bot menu commands set up successfully")

async def post_init(application):
    """Called after the application is initialized."""
    await setup_bot_menu(application)

def main():
    """Start the bot."""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        return
    
    jiak_ai = JiakAI()
    
    application = Application.builder().token(token).post_init(post_init).build()
    
    application.add_handler(CommandHandler("start", jiak_ai.start))
    application.add_handler(CommandHandler("help", jiak_ai.help_command))
    application.add_handler(CommandHandler("summary", jiak_ai.summary_command))
    application.add_handler(CommandHandler("history", jiak_ai.history_command))
    application.add_handler(CommandHandler("request_access", jiak_ai.request_access_command))
    application.add_handler(CallbackQueryHandler(jiak_ai.handle_callback))
    application.add_handler(MessageHandler(filters.PHOTO, jiak_ai.handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, jiak_ai.handle_text))
    
    logger.info("Starting JiakAI bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()