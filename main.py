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
        success = await log_access_request(
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

    async def add_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add a user to authorized list - Admin only."""
        if not update.effective_user or not update.message:
            return

        admin_user_id = str(update.effective_user.id)

        # Check if sender is authorized (admin check)
        from src.utils.access_control import check_user_access_async
        if not await check_user_access_async(admin_user_id):
            await update.message.reply_text("❌ You don't have permission to use admin commands.")
            return

        # Parse command arguments
        args = context.args
        if not args:
            await update.message.reply_text(
                "📝 Usage: /add_user <telegram_id>\n\n"
                "Example: /add_user 123456789"
            )
            return

        target_user_id = args[0].strip()

        try:
            # Add user to Firebase
            success = await self.firebase_service.add_authorized_user(target_user_id, admin_user_id)

            if success:
                await update.message.reply_text(
                    f"✅ User {target_user_id} has been added to authorized users.\n"
                    f"They can now use the bot."
                )
            else:
                await update.message.reply_text(f"❌ Failed to add user {target_user_id}. Please try again.")

        except Exception as e:
            logger.error(f"Error in add_user command: {e}")
            await update.message.reply_text("❌ An error occurred while adding the user.")

    async def remove_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove a user from authorized list - Admin only."""
        if not update.effective_user or not update.message:
            return

        admin_user_id = str(update.effective_user.id)

        # Check if sender is authorized (admin check)
        from src.utils.access_control import check_user_access_async
        if not await check_user_access_async(admin_user_id):
            await update.message.reply_text("❌ You don't have permission to use admin commands.")
            return

        # Parse command arguments
        args = context.args
        if not args:
            await update.message.reply_text(
                "📝 Usage: /remove_user <telegram_id>\n\n"
                "Example: /remove_user 123456789"
            )
            return

        target_user_id = args[0].strip()

        try:
            # Remove user from Firebase
            success = await self.firebase_service.remove_authorized_user(target_user_id, admin_user_id)

            if success:
                await update.message.reply_text(
                    f"✅ User {target_user_id} has been removed from authorized users.\n"
                    f"They can no longer use the bot."
                )
            else:
                await update.message.reply_text(f"❌ Failed to remove user {target_user_id}. Please try again.")

        except Exception as e:
            logger.error(f"Error in remove_user command: {e}")
            await update.message.reply_text("❌ An error occurred while removing the user.")

    async def list_users_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all authorized users - Admin only."""
        if not update.effective_user or not update.message:
            return

        admin_user_id = str(update.effective_user.id)

        # Check if sender is authorized (admin check)
        from src.utils.access_control import check_user_access_async
        if not await check_user_access_async(admin_user_id):
            await update.message.reply_text("❌ You don't have permission to use admin commands.")
            return

        try:
            # Get authorized users from Firebase
            users = await self.firebase_service.list_authorized_users()

            if not users:
                await update.message.reply_text("📝 No authorized users found in Firebase.")
                return

            response = f"👥 Authorized Users ({len(users)} total):\n\n"

            for i, user in enumerate(users[:10], 1):  # Limit to first 10 users
                user_id = user.get('user_id', 'Unknown')
                added_at = user.get('added_at', 'Unknown')
                added_by = user.get('added_by', 'Unknown')

                if isinstance(added_at, datetime):
                    added_at_str = added_at.strftime('%Y-%m-%d %H:%M')
                else:
                    added_at_str = str(added_at)

                response += f"{i}. User ID: `{user_id}`\n"
                response += f"   Added: {added_at_str}\n"
                response += f"   Added by: {added_by}\n\n"

            if len(users) > 10:
                response += f"... and {len(users) - 10} more users"

            await update.message.reply_text(response, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in list_users command: {e}")
            await update.message.reply_text("❌ An error occurred while listing users.")

    async def reload_access_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reload access control cache - Admin only."""
        if not update.effective_user or not update.message:
            return

        admin_user_id = str(update.effective_user.id)

        # Check if sender is authorized (admin check)
        from src.utils.access_control import check_user_access_async
        if not await check_user_access_async(admin_user_id):
            await update.message.reply_text("❌ You don't have permission to use admin commands.")
            return

        try:
            # Note: Cache refresh is no longer needed with direct Firebase checking
            user_count = 0

            await update.message.reply_text(
                f"ℹ️ Access control now uses direct Firebase checking.\n"
                f"No cache refresh needed - access is always current!"
            )

        except Exception as e:
            logger.error(f"Error in reload_access command: {e}")
            await update.message.reply_text("❌ An error occurred while reloading access control.")

    async def migrate_users_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Migrate users from environment to Firebase - Admin only."""
        if not update.effective_user or not update.message:
            return

        admin_user_id = str(update.effective_user.id)

        # Check if sender is authorized (admin check)
        from src.utils.access_control import check_user_access_async
        if not await check_user_access_async(admin_user_id):
            await update.message.reply_text("❌ You don't have permission to use admin commands.")
            return

        try:
            # Migrate users from environment to Firebase
            migrated_count = await self.firebase_service.migrate_env_users_to_firebase()

            if migrated_count > 0:
                await update.message.reply_text(
                    f"✅ Migration completed!\n"
                    f"📊 Migrated {migrated_count} users from environment to Firebase.\n\n"
                    f"🔄 Refreshing access control cache..."
                )
                await update.message.reply_text("✅ Migration complete - access control updated!")
            else:
                await update.message.reply_text(
                    "ℹ️ No new users to migrate.\n"
                    "All users from environment variable are already in Firebase."
                )

        except Exception as e:
            logger.error(f"Error in migrate_users command: {e}")
            await update.message.reply_text("❌ An error occurred during migration.")

    async def inspect_users_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inspect users collection to see existing requests - Admin only."""
        if not update.effective_user or not update.message:
            return

        admin_user_id = str(update.effective_user.id)

        # Check if sender is authorized (admin check)
        from src.utils.access_control import check_user_access_async
        if not await check_user_access_async(admin_user_id):
            await update.message.reply_text("❌ You don't have permission to use admin commands.")
            return

        try:
            await update.message.reply_text("🔍 Inspecting users collection...")

            # Inspect the users collection
            inspection_result = await self.firebase_service.inspect_users_collection()

            if 'error' in inspection_result:
                await update.message.reply_text(f"❌ Error inspecting users collection: {inspection_result['error']}")
                return

            total_users = inspection_result.get('total_users', 0)
            sample_users = inspection_result.get('sample_users', [])

            response = f"🔍 **Users Collection Inspection**\n\n"
            response += f"📊 Total users in collection: {total_users}\n\n"

            if sample_users:
                response += "📋 Sample users (first 10):\n\n"
                for i, user in enumerate(sample_users, 1):
                    user_id = user['user_id']
                    fields = user.get('fields', [])

                    # Escape field names to avoid markdown issues
                    safe_fields = [field.replace('_', '\\_') for field in fields]

                    response += f"{i}. User `{user_id}`:\n"
                    response += f"   • Has username: {user.get('has_username', False)}\n"
                    response += f"   • Has name: {user.get('has_first_name', False)}\n"
                    response += f"   • Is regular user: {user.get('has_created_at', False)}\n"
                    response += f"   • Fields: {', '.join(safe_fields)}\n\n"
            else:
                response += "📝 No users found in collection.\n"

            await update.message.reply_text(response, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in inspect_users command: {e}")
            await update.message.reply_text("❌ An error occurred while inspecting users collection.")

    async def migrate_requests_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Migrate user requests to access_requests collection - Admin only."""
        if not update.effective_user or not update.message:
            return

        admin_user_id = str(update.effective_user.id)

        # Check if sender is authorized (admin check)
        from src.utils.access_control import check_user_access_async
        if not await check_user_access_async(admin_user_id):
            await update.message.reply_text("❌ You don't have permission to use admin commands.")
            return

        try:
            await update.message.reply_text("🚚 Starting migration from users to access_requests...")

            # Perform migration
            migration_result = await self.firebase_service.migrate_users_to_access_requests()

            migrated = migration_result.get('migrated', 0)
            skipped = migration_result.get('skipped', 0)
            errors = migration_result.get('errors', 0)
            total_processed = migration_result.get('total_processed', 0)

            response = f"✅ **Migration Completed**\n\n"
            response += f"📊 **Results:**\n"
            response += f"• Migrated: {migrated} requests\n"
            response += f"• Skipped: {skipped} users (already exist or regular users)\n"
            response += f"• Errors: {errors}\n"
            response += f"• Total processed: {total_processed}\n\n"

            if migrated > 0:
                response += f"🎉 Successfully migrated {migrated} requests!\n"
                response += f"You can now use `/list_requests` to see them."
            elif skipped > 0:
                response += f"ℹ️ Found {skipped} users but they appear to be regular users, not access requests."
            else:
                response += f"📝 No access requests found to migrate."

            await update.message.reply_text(response, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in migrate_requests command: {e}")
            await update.message.reply_text("❌ An error occurred during requests migration.")

    async def admin_panel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show admin control panel - Admin only."""
        if not update.effective_user or not update.message:
            return

        admin_user_id = str(update.effective_user.id)

        # Check if user is admin (environment variable check)
        if not is_admin(admin_user_id):
            await update.message.reply_text("❌ Access denied. Admin privileges required.")
            return

        try:
            # Get pending requests count
            pending_requests = await self.firebase_service.get_access_requests(status='pending')
            approved_users = await self.firebase_service.get_access_requests(status='approved')

            response = f"👑 **Admin Control Panel**\n\n"
            response += f"📊 **Quick Stats:**\n"
            response += f"• Pending requests: {len(pending_requests)}\n"
            response += f"• Approved users: {len(approved_users)}\n\n"
            response += f"🎛️ **Available Commands:**\n"
            response += f"• `/list_requests` - Review pending access requests\n"
            response += f"• `/manage_users` - Manage user access permissions\n"
            response += f"• `/reload_access` - Refresh access cache\n"

            await update.message.reply_text(response, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in admin_panel command: {e}")
            await update.message.reply_text("❌ An error occurred while loading admin panel.")

    async def list_requests_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List pending access requests with one-click approve/deny - Admin only."""
        if not update.effective_user or not update.message:
            return

        admin_user_id = str(update.effective_user.id)

        # Check if user is admin (environment variable check)
        if not is_admin(admin_user_id):
            await update.message.reply_text("❌ Access denied. Admin privileges required.")
            return

        try:
            # Get pending access requests
            requests = await self.firebase_service.get_access_requests(status='pending')

            if not requests:
                await update.message.reply_text(
                    "📝 No pending access requests.\n\n"
                    "💡 Users can request access with /request_access"
                )
                return

            # Create response with inline buttons for each request
            response = f"📋 **Pending Access Requests** ({len(requests)} total):\n\n"

            keyboard = []

            for i, request in enumerate(requests[:5], 1):  # Limit to 5 requests per message
                user_id = request.get('user_id', 'Unknown')
                display_name = request.get('display_name', 'Unknown User')
                requested_at = request.get('requested_at', 'Unknown')

                if isinstance(requested_at, datetime):
                    requested_at_str = requested_at.strftime('%m-%d %H:%M')
                else:
                    requested_at_str = str(requested_at)[:10] if requested_at else 'Unknown'

                response += f"{i}. **{display_name}**\n"
                response += f"   ID: `{user_id}`\n"
                response += f"   Requested: {requested_at_str}\n\n"

                # Add approve/deny buttons for this request
                keyboard.append([
                    InlineKeyboardButton(
                        f"✅ Approve {display_name[:15]}{'...' if len(display_name) > 15 else ''}",
                        callback_data=f"approve_user_{user_id}"
                    ),
                    InlineKeyboardButton(
                        f"❌ Deny {display_name[:15]}{'...' if len(display_name) > 15 else ''}",
                        callback_data=f"deny_user_{user_id}"
                    )
                ])

            if len(requests) > 5:
                response += f"... and {len(requests) - 5} more requests\n"

            # Add bulk actions
            if len(requests) > 1:
                keyboard.append([
                    InlineKeyboardButton("✅ Approve All", callback_data="approve_all_users"),
                    InlineKeyboardButton("❌ Deny All", callback_data="deny_all_users")
                ])

            keyboard.append([
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh_requests")
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in list_requests command: {e}")
            await update.message.reply_text("❌ An error occurred while listing access requests.")

    async def manage_users_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manage user access permissions - Admin only."""
        if not update.effective_user or not update.message:
            return

        admin_user_id = str(update.effective_user.id)

        # Check if user is admin (environment variable check)
        if not is_admin(admin_user_id):
            await update.message.reply_text("❌ Access denied. Admin privileges required.")
            return

        try:
            # Get all users with access info
            users = await self.firebase_service.get_all_users_with_access_info()

            if not users:
                await update.message.reply_text("📝 No users found in system.")
                return

            # Separate by status
            approved_users = [u for u in users if u.get('access_status') == 'approved']
            pending_users = [u for u in users if u.get('access_status') == 'pending']
            revoked_users = [u for u in users if u.get('access_status') == 'revoked']
            reinstate_users = [u for u in users if u.get('access_status') == 'reinstate_request']

            response = f"👥 **User Access Management**\n\n"
            response += f"📊 **Status Summary:**\n"
            response += f"• ✅ Approved: {len(approved_users)}\n"
            response += f"• ⏳ Pending: {len(pending_users)}\n"
            response += f"• 🚫 Revoked: {len(revoked_users)}\n"
            response += f"• 🔄 Reinstate Requests: {len(reinstate_users)}\n\n"

            keyboard = []

            if approved_users:
                keyboard.append([
                    InlineKeyboardButton("✅ View Approved Users", callback_data="view_approved_users")
                ])

            if pending_users:
                keyboard.append([
                    InlineKeyboardButton("⏳ View Pending Requests", callback_data="view_pending_users")
                ])

            if revoked_users:
                keyboard.append([
                    InlineKeyboardButton("🚫 View Revoked Users", callback_data="view_revoked_users")
                ])

            if reinstate_users:
                keyboard.append([
                    InlineKeyboardButton("🔄 View Reinstate Requests", callback_data="view_reinstate_users")
                ])

            keyboard.append([
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh_user_management")
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in manage_users command: {e}")
            await update.message.reply_text("❌ An error occurred while loading user management.")

    async def list_requests_command_old(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List pending access requests with one-click approve/deny - Admin only."""
        if not update.effective_user or not update.message:
            return

        admin_user_id = str(update.effective_user.id)

        # Check if sender is authorized (admin check)
        from src.utils.access_control import check_user_access_async
        if not await check_user_access_async(admin_user_id):
            await update.message.reply_text("❌ You don't have permission to use admin commands.")
            return

        try:
            # Get pending access requests from Firebase
            requests = await self.firebase_service.get_access_requests(status='pending')

            if not requests:
                await update.message.reply_text(
                    "📝 No pending access requests.\n\n"
                    "💡 Users can request access with /request_access"
                )
                return

            # Create response with inline buttons for each request
            response = f"📋 Pending Access Requests ({len(requests)} total):\n\n"

            keyboard = []

            for i, request in enumerate(requests[:5], 1):  # Limit to 5 requests per message
                user_id = request.get('user_id', 'Unknown')
                display_name = request.get('display_name', 'Unknown User')
                requested_at = request.get('requested_at', 'Unknown')

                if isinstance(requested_at, datetime):
                    requested_at_str = requested_at.strftime('%m-%d %H:%M')
                else:
                    requested_at_str = str(requested_at)[:10]

                response += f"{i}. **{display_name}**\n"
                response += f"   ID: `{user_id}`\n"
                response += f"   Requested: {requested_at_str}\n\n"

                # Add approve/deny buttons for this request
                keyboard.append([
                    InlineKeyboardButton(
                        f"✅ Approve {display_name[:15]}{'...' if len(display_name) > 15 else ''}",
                        callback_data=f"approve_request_{user_id}"
                    ),
                    InlineKeyboardButton(
                        f"❌ Deny {display_name[:15]}{'...' if len(display_name) > 15 else ''}",
                        callback_data=f"deny_request_{user_id}"
                    )
                ])

            if len(requests) > 5:
                response += f"... and {len(requests) - 5} more requests\n"
                keyboard.append([
                    InlineKeyboardButton("📄 View More", callback_data="view_more_requests")
                ])

            # Add bulk actions
            if len(requests) > 1:
                keyboard.append([
                    InlineKeyboardButton("✅ Approve All", callback_data="approve_all_requests"),
                    InlineKeyboardButton("❌ Deny All", callback_data="deny_all_requests")
                ])

            keyboard.append([
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh_requests")
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in list_requests command: {e}")
            await update.message.reply_text("❌ An error occurred while listing access requests.")

    async def quick_add_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Quick add users from recent requests - Admin only."""
        if not update.effective_user or not update.message:
            return

        admin_user_id = str(update.effective_user.id)

        # Check if sender is authorized (admin check)
        from src.utils.access_control import check_user_access_async
        if not await check_user_access_async(admin_user_id):
            await update.message.reply_text("❌ You don't have permission to use admin commands.")
            return

        try:
            # Get recent pending requests
            requests = await self.firebase_service.get_access_requests(status='pending')

            if not requests:
                await update.message.reply_text(
                    "📝 No pending requests to add.\n\n"
                    "💡 Use /list_requests to see pending access requests"
                )
                return

            # Create quick-add buttons for each request
            keyboard = []
            response = f"⚡ Quick Add Users ({len(requests)} pending):\n\n"

            for i, request in enumerate(requests[:6], 1):  # Limit to 6 for better UI
                user_id = request.get('user_id', 'Unknown')
                display_name = request.get('display_name', 'Unknown User')

                response += f"{i}. {display_name} (`{user_id}`)\n"

                # Create quick add button
                button_text = f"➕ Add {display_name[:20]}{'...' if len(display_name) > 20 else ''}"
                keyboard.append([
                    InlineKeyboardButton(button_text, callback_data=f"quick_add_{user_id}")
                ])

            if len(requests) > 6:
                response += f"\n... and {len(requests) - 6} more\n"

            # Add bulk action
            if len(requests) > 1:
                keyboard.append([
                    InlineKeyboardButton("✅ Add All Pending", callback_data="quick_add_all")
                ])

            keyboard.append([
                InlineKeyboardButton("📋 View Full Requests", callback_data="view_full_requests")
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in quick_add command: {e}")
            await update.message.reply_text("❌ An error occurred while loading quick add options.")

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
            portion_data = analysis_result.get('portion_data', {'overall_multiplier': 1.0})
            portion_multiplier = portion_data.get('overall_multiplier', 1.0)

            nutrition_data = await self.nutritionix_service.get_nutrition_data(food_description, portion_multiplier)
            
            # Store pending meal data in context for confirmation
            # Extract raw nutrition data if available
            raw_nutrition = nutrition_data.get('raw_nutrition', {})

            pending_meal = {
                'timestamp': datetime.now(),
                'input_type': 'photo',
                'input_value': photo.file_id,
                'food_description': food_description,
                'nutrition': nutrition_data,
                'user_id': user_id,
                'confidence': confidence,
                'portion_multiplier': portion_multiplier,
                'portion_data': portion_data,
                'raw_nutrition': raw_nutrition
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

        # Check if user is entering a custom portion multiplier
        if 'custom_portion_meal_id' in context.user_data:
            await self._handle_custom_portion_input(update, context, text)
            return

        try:
            await update.message.reply_text("💬 Analyzing your meal description...")
            
            analysis_result = await self.openai_service.analyze_food_text(text)

            # Handle edge cases - no food detected or analysis failed
            if not analysis_result['success']:
                await self._handle_analysis_failure(update, analysis_result)
                return

            food_description = analysis_result['description']
            confidence = analysis_result['confidence']
            portion_data = analysis_result.get('portion_data', {'overall_multiplier': 1.0})
            portion_multiplier = portion_data.get('overall_multiplier', 1.0)

            nutrition_data = await self.nutritionix_service.get_nutrition_data(food_description, portion_multiplier)
            
            # Store pending meal data in context for confirmation
            # Extract raw nutrition data if available
            raw_nutrition = nutrition_data.get('raw_nutrition', {})

            pending_meal = {
                'timestamp': datetime.now(),
                'input_type': 'text',
                'input_value': text,
                'food_description': food_description,
                'nutrition': nutrition_data,
                'user_id': user_id,
                'confidence': confidence,
                'portion_multiplier': portion_multiplier,
                'portion_data': portion_data,
                'raw_nutrition': raw_nutrition
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
        elif data == 'request_reinstate':
            await self._handle_request_reinstate(query, context)
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
        elif data.startswith('custom_portion_'):
            await self._handle_custom_portion(query, context, data)
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
        elif data.startswith('approve_user_'):
            await self._handle_approve_user(query, context, data)
        elif data.startswith('approve_request_'):
            await self._handle_approve_request(query, context, data)
        elif data.startswith('deny_user_'):
            await self._handle_deny_user(query, context, data)
        elif data.startswith('deny_request_'):
            await self._handle_deny_request(query, context, data)
        elif data.startswith('revoke_user_'):
            await self._handle_revoke_user(query, context, data)
        elif data == 'approve_all_users':
            await self._handle_approve_all_users(query, context)
        elif data == 'deny_all_users':
            await self._handle_deny_all_users(query, context)
        elif data == 'refresh_requests':
            await self._handle_refresh_requests(query, context)
        elif data == 'refresh_user_management':
            await self._handle_refresh_user_management(query, context)
        elif data == 'view_approved_users':
            await self._handle_view_approved_users(query, context)
        elif data == 'view_pending_users':
            await self._handle_view_pending_users(query, context)
        elif data == 'view_revoked_users':
            await self._handle_view_revoked_users(query, context)
        elif data == 'view_reinstate_users':
            await self._handle_view_reinstate_users(query, context)
        elif data.startswith('reapprove_user_'):
            await self._handle_reapprove_user(query, context, data)
        elif data.startswith('approve_reinstate_'):
            await self._handle_approve_reinstate(query, context, data)
        elif data.startswith('deny_reinstate_'):
            await self._handle_deny_reinstate(query, context, data)

    async def _handle_approve_user(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle user approval."""
        user_id = data.replace('approve_user_', '')
        admin_user_id = str(query.from_user.id)

        try:
            # Approve user access
            success = await self.firebase_service.approve_user_access(user_id, admin_user_id)

            if success:

                # Send notification to user
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            "🎉 **Access Approved!**\n\n"
                            "Welcome to JiakAI! Your access request has been approved.\n\n"
                            "You can now:\n"
                            "• Track meals by sending photos or descriptions\n"
                            "• View your nutrition history with /history\n"
                            "• Get meal summaries and insights\n\n"
                            "Start by sending a photo of your meal or describing what you ate! 🍽️"
                        ),
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Could not notify user {user_id}: {e}")

                await query.edit_message_text(
                    f"✅ **User Approved**\n\n"
                    f"User {user_id} has been approved for access.\n"
                    f"They can now use the bot.\n\n"
                    f"📬 User has been notified.\n"
                    f"✅ Access updated in Firebase."
                )
            else:
                await query.edit_message_text("❌ Failed to approve user. Please try again.")

        except Exception as e:
            logger.error(f"Error approving user: {e}")
            await query.edit_message_text("❌ An error occurred while approving the user.")

    async def _handle_approve_request(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle access request approval."""
        user_id = data.replace('approve_request_', '')

        try:
            # Update access request status to approved
            access_request_ref = self.firebase_service.db.collection('access_requests').document(user_id)
            access_request_ref.update({
                'status': 'approved',
                'approved_at': datetime.now()
            })


            # Get user details for notification
            user_doc = access_request_ref.get()
            user_data = user_doc.to_dict() if user_doc.exists else {}
            display_name = user_data.get('display_name', user_id)

            # Send notification to the user
            try:
                await self.send_message(
                    chat_id=int(user_id),
                    text=(
                        "🎉 **Access Approved!**\n\n"
                        "Your access request has been approved! You can now use all JiakAI features.\n\n"
                        "Try /start to begin using the bot."
                    ),
                    parse_mode='Markdown'
                )
            except Exception as notification_error:
                logger.warning(f"Could not send approval notification to user {user_id}: {notification_error}")

            await query.edit_message_text(
                f"✅ **Access Request Approved**\n\n"
                f"User {display_name} ({user_id}) has been approved and notified."
            )

        except Exception as e:
            logger.error(f"Error approving access request: {e}")
            await query.edit_message_text("❌ An error occurred while approving the access request.")

    async def _handle_deny_user(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle user denial."""
        user_id = data.replace('deny_user_', '')

        try:
            # Update access request status to denied
            access_request_ref = self.firebase_service.db.collection('access_requests').document(user_id)
            access_request_ref.update({
                'status': 'denied',
                'denied_at': datetime.now()
            })

            await query.edit_message_text(
                f"❌ **User Denied**\n\n"
                f"Access request from user {user_id} has been denied."
            )

        except Exception as e:
            logger.error(f"Error denying user: {e}")
            await query.edit_message_text("❌ An error occurred while denying the user.")

    async def _handle_deny_request(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle access request denial."""
        user_id = data.replace('deny_request_', '')

        try:
            # Update access request status to denied
            access_request_ref = self.firebase_service.db.collection('access_requests').document(user_id)
            access_request_ref.update({
                'status': 'denied',
                'denied_at': datetime.now()
            })

            await query.edit_message_text(
                f"❌ **Access Request Denied**\n\n"
                f"Access request from user {user_id} has been denied."
            )

        except Exception as e:
            logger.error(f"Error denying access request: {e}")
            await query.edit_message_text("❌ An error occurred while denying the access request.")

    async def _handle_revoke_user(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle user access revocation."""
        user_id = data.replace('revoke_user_', '')
        admin_user_id = str(query.from_user.id)

        try:
            # Revoke user access
            success = await self.firebase_service.revoke_user_access(user_id, admin_user_id)

            if success:

                await query.edit_message_text(
                    f"🚫 **User Access Revoked**\n\n"
                    f"User {user_id} access has been revoked.\n"
                    f"They can no longer use the bot.\n\n"
                    f"✅ Access updated in Firebase."
                )
            else:
                await query.edit_message_text("❌ Failed to revoke user access. Please try again.")

        except Exception as e:
            logger.error(f"Error revoking user access: {e}")
            await query.edit_message_text("❌ An error occurred while revoking user access.")

    async def _handle_reapprove_user(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle user re-approval from revoked status."""
        user_id = data.replace('reapprove_user_', '')
        admin_user_id = str(query.from_user.id)

        try:
            # Re-approve user access (similar to approve_user_access)
            success = await self.firebase_service.approve_user_access(user_id, admin_user_id)

            if success:

                # Send notification to user
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            "🎉 **Access Restored!**\n\n"
                            "Your access to JiakAI has been restored!\n"
                            "You can now use the bot again.\n\n"
                            "Welcome back! 🙌"
                        ),
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Could not notify user {user_id}: {e}")

                await query.edit_message_text(
                    f"✅ **User Re-approved**\n\n"
                    f"User {user_id} has been re-approved!\n"
                    f"They can now use the bot again.\n\n"
                    f"📬 User has been notified.\n"
                    f"✅ Access updated in Firebase."
                )
            else:
                await query.edit_message_text("❌ Failed to re-approve user. Please try again.")

        except Exception as e:
            logger.error(f"Error re-approving user: {e}")
            await query.edit_message_text("❌ An error occurred while re-approving user.")

    async def _handle_approve_reinstate(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle approval of reinstatement request."""
        user_id = data.replace('approve_reinstate_', '')
        admin_user_id = str(query.from_user.id)

        try:
            # Approve the reinstatement (same as normal approval)
            success = await self.firebase_service.approve_user_access(user_id, admin_user_id)

            if success:

                # Send notification to user
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            "🎉 **Access Reinstated!**\n\n"
                            "Your access to JiakAI has been restored!\n"
                            "You can now use the bot again.\n\n"
                            "Welcome back! 🙌"
                        ),
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Could not notify user {user_id}: {e}")

                await query.edit_message_text(
                    f"✅ **Reinstatement Approved**\n\n"
                    f"User {user_id} has been reinstated!\n"
                    f"They can now use the bot again.\n\n"
                    f"📬 User has been notified.\n"
                    f"✅ Access updated in Firebase."
                )
            else:
                await query.edit_message_text("❌ Failed to approve reinstatement. Please try again.")

        except Exception as e:
            logger.error(f"Error approving reinstatement for user {user_id}: {e}")
            await query.edit_message_text("❌ An error occurred while approving reinstatement.")

    async def _handle_deny_reinstate(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle denial of reinstatement request."""
        user_id = data.replace('deny_reinstate_', '')

        try:
            # Update status back to denied (permanently denied)
            access_request_ref = self.firebase_service.db.collection('access_requests').document(user_id)
            access_request_ref.update({
                'status': 'denied',
                'denied_at': datetime.now()
            })

            await query.edit_message_text(
                f"❌ **Reinstatement Denied**\n\n"
                f"Reinstatement request for user {user_id} has been denied."
            )

        except Exception as e:
            logger.error(f"Error denying reinstatement for user {user_id}: {e}")
            await query.edit_message_text("❌ An error occurred while denying reinstatement.")

    async def _handle_view_approved_users(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle view approved users."""
        try:
            approved_users = await self.firebase_service.get_access_requests(status='approved')

            if not approved_users:
                await query.edit_message_text("📝 No approved users found.")
                return

            response = f"✅ **Approved Users** ({len(approved_users)} total):\n\n"

            keyboard = []
            for i, user in enumerate(approved_users[:5], 1):
                user_id = user.get('user_id', 'Unknown')
                display_name = user.get('display_name', 'Unknown User')

                response += f"{i}. **{display_name}**\n"
                response += f"   ID: `{user_id}`\n"

                # Add revoke button
                keyboard.append([
                    InlineKeyboardButton(
                        f"🚫 Revoke {display_name[:15]}{'...' if len(display_name) > 15 else ''}",
                        callback_data=f"revoke_user_{user_id}"
                    )
                ])

            if len(approved_users) > 5:
                response += f"\n... and {len(approved_users) - 5} more users"

            keyboard.append([
                InlineKeyboardButton("🔙 Back to User Management", callback_data="refresh_user_management")
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(response, reply_markup=reply_markup, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error viewing approved users: {e}")
            await query.edit_message_text("❌ An error occurred while loading approved users.")

    async def _handle_view_pending_users(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle view pending users (same as refresh requests)."""
        await self._handle_refresh_requests(query, context)

    async def _handle_view_revoked_users(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle view revoked users."""
        try:
            revoked_users = await self.firebase_service.get_access_requests(status='revoked')

            if not revoked_users:
                await query.edit_message_text("📝 No revoked users found.")
                return

            response = f"🚫 **Revoked Users** ({len(revoked_users)} total):\n\n"

            keyboard = []

            for i, user in enumerate(revoked_users[:5], 1):  # Limit to 5 for buttons
                user_id = user.get('user_id', 'Unknown')
                display_name = user.get('display_name', 'Unknown User')
                revoked_at = user.get('revoked_at')

                response += f"{i}. **{display_name}**\n"
                response += f"   ID: `{user_id}`\n"
                if revoked_at:
                    if isinstance(revoked_at, datetime):
                        response += f"   Revoked: {revoked_at.strftime('%m-%d %H:%M')}\n"
                response += "\n"

                # Add re-approve button for each user
                keyboard.append([
                    InlineKeyboardButton(
                        f"🔄 Re-approve {display_name[:15]}{'...' if len(display_name) > 15 else ''}",
                        callback_data=f"reapprove_user_{user_id}"
                    )
                ])

            if len(revoked_users) > 5:
                response += f"... and {len(revoked_users) - 5} more users\n"

            keyboard.append([
                InlineKeyboardButton("🔙 Back to User Management", callback_data="refresh_user_management")
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(response, reply_markup=reply_markup, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error viewing revoked users: {e}")
            await query.edit_message_text("❌ An error occurred while loading revoked users.")

    async def _handle_view_reinstate_users(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle view reinstate request users."""
        try:
            reinstate_users = await self.firebase_service.get_access_requests(status='reinstate_request')

            if not reinstate_users:
                await query.edit_message_text("📝 No reinstatement requests found.")
                return

            response = f"🔄 **Reinstate Requests** ({len(reinstate_users)} total):\n\n"

            keyboard = []

            for i, user in enumerate(reinstate_users[:5], 1):  # Limit to 5 for buttons
                user_id = user.get('user_id', 'Unknown')
                display_name = user.get('display_name', 'Unknown User')
                reinstate_requested_at = user.get('reinstate_requested_at')

                response += f"{i}. **{display_name}**\n"
                response += f"   ID: `{user_id}`\n"
                if reinstate_requested_at:
                    if isinstance(reinstate_requested_at, datetime):
                        response += f"   Requested: {reinstate_requested_at.strftime('%m-%d %H:%M')}\n"
                response += "\n"

                # Add approve/deny buttons for each reinstatement request
                keyboard.append([
                    InlineKeyboardButton(
                        f"✅ Approve {display_name[:15]}{'...' if len(display_name) > 15 else ''}",
                        callback_data=f"approve_reinstate_{user_id}"
                    ),
                    InlineKeyboardButton(
                        f"❌ Deny {display_name[:15]}{'...' if len(display_name) > 15 else ''}",
                        callback_data=f"deny_reinstate_{user_id}"
                    )
                ])

            if len(reinstate_users) > 5:
                response += f"... and {len(reinstate_users) - 5} more requests\n"

            keyboard.append([
                InlineKeyboardButton("🔙 Back to User Management", callback_data="refresh_user_management")
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(response, reply_markup=reply_markup, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error viewing reinstate users: {e}")
            await query.edit_message_text("❌ An error occurred while loading reinstatement requests.")

    async def _handle_refresh_user_management(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle refresh user management (redirect to manage users)."""
        # Simulate the manage_users command
        try:
            users = await self.firebase_service.get_all_users_with_access_info()

            if not users:
                await query.edit_message_text("📝 No users found in system.")
                return

            # Separate by status
            approved_users = [u for u in users if u.get('access_status') == 'approved']
            pending_users = [u for u in users if u.get('access_status') == 'pending']
            revoked_users = [u for u in users if u.get('access_status') == 'revoked']

            response = f"👥 **User Access Management**\n\n"
            response += f"📊 **Status Summary:**\n"
            response += f"• ✅ Approved: {len(approved_users)}\n"
            response += f"• ⏳ Pending: {len(pending_users)}\n"
            response += f"• 🚫 Revoked: {len(revoked_users)}\n\n"

            keyboard = []

            if approved_users:
                keyboard.append([
                    InlineKeyboardButton("✅ View Approved Users", callback_data="view_approved_users")
                ])

            if pending_users:
                keyboard.append([
                    InlineKeyboardButton("⏳ View Pending Requests", callback_data="view_pending_users")
                ])

            if revoked_users:
                keyboard.append([
                    InlineKeyboardButton("🚫 View Revoked Users", callback_data="view_revoked_users")
                ])

            keyboard.append([
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh_user_management")
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(response, reply_markup=reply_markup, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error refreshing user management: {e}")
            await query.edit_message_text("❌ An error occurred while refreshing user management.")

    async def _handle_quick_add(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle quick add user."""
        user_id = data.replace('quick_add_', '')
        admin_user_id = str(query.from_user.id)

        try:
            # Add user to authorized list
            success = await self.firebase_service.add_authorized_user(user_id, admin_user_id)

            if success:
                # Update request status
                await self.firebase_service.update_access_request_status(user_id, 'approved')

                await query.edit_message_text(
                    f"⚡ **Quick Add Successful**\n\n"
                    f"User {user_id} has been quickly added.\n"
                    f"They can now use the bot immediately.\n\n"
                    f"🔄 Access control updated."
                )
            else:
                await query.edit_message_text("❌ Failed to add user. Please try again.")

        except Exception as e:
            logger.error(f"Error in quick add: {e}")
            await query.edit_message_text("❌ An error occurred during quick add.")

    async def _handle_approve_all_requests(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle approve all requests."""
        admin_user_id = str(query.from_user.id)

        try:
            # Get all pending requests
            requests = await self.firebase_service.get_access_requests(status='pending')

            if not requests:
                await query.edit_message_text("📝 No pending requests to approve.")
                return

            approved_count = 0
            for request in requests:
                user_id = request.get('user_id')
                if user_id:
                    # Add user and update status
                    add_success = await self.firebase_service.add_authorized_user(user_id, admin_user_id)
                    status_success = await self.firebase_service.update_access_request_status(user_id, 'approved')

                    if add_success and status_success:
                        approved_count += 1


            await query.edit_message_text(
                f"✅ **Bulk Approval Complete**\n\n"
                f"Approved {approved_count} out of {len(requests)} requests.\n"
                f"All approved users can now use the bot.\n\n"
                f"✅ Access updated in Firebase."
            )

        except Exception as e:
            logger.error(f"Error in bulk approval: {e}")
            await query.edit_message_text("❌ An error occurred during bulk approval.")

    async def _handle_deny_all_requests(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle deny all requests."""
        try:
            # Get all pending requests
            requests = await self.firebase_service.get_access_requests(status='pending')

            if not requests:
                await query.edit_message_text("📝 No pending requests to deny.")
                return

            denied_count = 0
            for request in requests:
                user_id = request.get('user_id')
                if user_id:
                    success = await self.firebase_service.update_access_request_status(user_id, 'denied')
                    if success:
                        denied_count += 1

            await query.edit_message_text(
                f"❌ **Bulk Denial Complete**\n\n"
                f"Denied {denied_count} out of {len(requests)} requests."
            )

        except Exception as e:
            logger.error(f"Error in bulk denial: {e}")
            await query.edit_message_text("❌ An error occurred during bulk denial.")

    async def _handle_quick_add_all(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle quick add all pending users."""
        admin_user_id = str(query.from_user.id)

        try:
            # Get all pending requests
            requests = await self.firebase_service.get_access_requests(status='pending')

            if not requests:
                await query.edit_message_text("📝 No pending requests to add.")
                return

            added_count = 0
            for request in requests:
                user_id = request.get('user_id')
                if user_id:
                    # Add user and update status
                    add_success = await self.firebase_service.add_authorized_user(user_id, admin_user_id)
                    status_success = await self.firebase_service.update_access_request_status(user_id, 'approved')

                    if add_success and status_success:
                        added_count += 1


            await query.edit_message_text(
                f"⚡ **Quick Add All Complete**\n\n"
                f"Added {added_count} out of {len(requests)} pending users.\n"
                f"All users can now use the bot immediately.\n\n"
                f"🔄 Access control updated."
            )

        except Exception as e:
            logger.error(f"Error in quick add all: {e}")
            await query.edit_message_text("❌ An error occurred during quick add all.")

    async def _handle_refresh_requests(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle refresh requests list."""
        # Simulate the list_requests command
        admin_user_id = str(query.from_user.id)

        try:
            # Get pending access requests from Firebase
            requests = await self.firebase_service.get_access_requests(status='pending')

            if not requests:
                await query.edit_message_text(
                    "📝 No pending access requests.\n\n"
                    "💡 Users can request access with /request_access"
                )
                return

            # Create response with inline buttons for each request
            response = f"📋 Pending Access Requests ({len(requests)} total):\n\n"

            keyboard = []

            for i, request in enumerate(requests[:5], 1):  # Limit to 5 requests per message
                user_id = request.get('user_id', 'Unknown')
                display_name = request.get('display_name', 'Unknown User')
                requested_at = request.get('requested_at', 'Unknown')

                if isinstance(requested_at, datetime):
                    requested_at_str = requested_at.strftime('%m-%d %H:%M')
                else:
                    requested_at_str = str(requested_at)[:10]

                response += f"{i}. **{display_name}**\n"
                response += f"   ID: `{user_id}`\n"
                response += f"   Requested: {requested_at_str}\n\n"

                # Add approve/deny buttons for this request
                keyboard.append([
                    InlineKeyboardButton(
                        f"✅ Approve {display_name[:15]}{'...' if len(display_name) > 15 else ''}",
                        callback_data=f"approve_request_{user_id}"
                    ),
                    InlineKeyboardButton(
                        f"❌ Deny {display_name[:15]}{'...' if len(display_name) > 15 else ''}",
                        callback_data=f"deny_request_{user_id}"
                    )
                ])

            if len(requests) > 5:
                response += f"... and {len(requests) - 5} more requests\n"

            # Add bulk actions
            if len(requests) > 1:
                keyboard.append([
                    InlineKeyboardButton("✅ Approve All", callback_data="approve_all_requests"),
                    InlineKeyboardButton("❌ Deny All", callback_data="deny_all_requests")
                ])

            keyboard.append([
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh_requests")
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(response, reply_markup=reply_markup, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error refreshing requests: {e}")
            await query.edit_message_text("❌ An error occurred while refreshing requests.")

    async def _handle_view_full_requests(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle view full requests from quick add."""
        # Redirect to full requests view
        await self._handle_refresh_requests(query, context)

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
                InlineKeyboardButton("0.25x", callback_data=f"portion_{meal_id}_0.25"),
                InlineKeyboardButton("0.33x", callback_data=f"portion_{meal_id}_0.33"),
                InlineKeyboardButton("0.5x", callback_data=f"portion_{meal_id}_0.5")
            ],
            [
                InlineKeyboardButton("0.67x", callback_data=f"portion_{meal_id}_0.67"),
                InlineKeyboardButton("0.75x", callback_data=f"portion_{meal_id}_0.75"),
                InlineKeyboardButton("1x", callback_data=f"portion_{meal_id}_1.0")
            ],
            [
                InlineKeyboardButton("1.25x", callback_data=f"portion_{meal_id}_1.25"),
                InlineKeyboardButton("1.5x", callback_data=f"portion_{meal_id}_1.5"),
                InlineKeyboardButton("1.75x", callback_data=f"portion_{meal_id}_1.75")
            ],
            [
                InlineKeyboardButton("2x", callback_data=f"portion_{meal_id}_2.0"),
                InlineKeyboardButton("2.5x", callback_data=f"portion_{meal_id}_2.5"),
                InlineKeyboardButton("3x", callback_data=f"portion_{meal_id}_3.0")
            ],
            [
                InlineKeyboardButton("✏️ Custom", callback_data=f"custom_portion_{meal_id}"),
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

    async def _handle_custom_portion(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle custom portion input request."""
        meal_id = data.replace('custom_portion_', '')

        # Store the meal_id for the next message
        context.user_data['custom_portion_meal_id'] = meal_id

        await query.edit_message_text(
            "✏️ Enter a custom portion multiplier:\n\n"
            "Examples:\n"
            "• 0.33 (1/3 portion)\n"
            "• 0.8 (80% of normal)\n"
            "• 1.2 (20% extra)\n"
            "• 2.5 (2.5x portion)\n\n"
            "Please type a number (0.1 to 10.0):"
        )

    async def _handle_custom_portion_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """Handle custom portion multiplier input."""
        meal_id = context.user_data.get('custom_portion_meal_id')
        if not meal_id:
            await update.message.reply_text("❌ Error: No meal ID found.")
            return

        try:
            # Parse the multiplier
            multiplier = float(text.strip())

            # Validate range
            if multiplier < 0.1 or multiplier > 10.0:
                await update.message.reply_text(
                    "❌ Invalid range. Please enter a number between 0.1 and 10.0.\n"
                    "Try again:"
                )
                return

            # Clear the custom portion state
            del context.user_data['custom_portion_meal_id']

            # Apply the custom portion (similar to _handle_portion_change)
            if 'pending_meals' not in context.user_data or meal_id not in context.user_data['pending_meals']:
                await update.message.reply_text("❌ Meal data not found. Please try again.")
                return

            meal_data = context.user_data['pending_meals'][meal_id]

            # Get the original food description (might have portion text appended)
            food_description = meal_data['food_description']

            # Try to get the base description without portion text
            if '(' in food_description and food_description.endswith(')'):
                # Remove portion text like " (1.5x portion)"
                base_description = food_description.split(' (')[0]
            else:
                base_description = food_description

            # Get new nutrition with custom multiplier
            nutrition_data = await self.nutritionix_service.get_nutrition_data(
                base_description,
                multiplier
            )

            meal_data['nutrition'] = nutrition_data
            meal_data['portion_multiplier'] = multiplier

            # Update food description to show custom portion
            original_description = base_description
            if multiplier == 1.0:
                portion_text = " (Normal portion)"
            elif multiplier < 0.5:
                portion_text = f" ({multiplier}x small portion)"
            elif multiplier > 2.0:
                portion_text = f" ({multiplier}x large portion)"
            else:
                portion_text = f" ({multiplier}x portion)"

            meal_data['food_description'] = original_description + portion_text

            # Show updated confirmation
            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{meal_id}"),
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
                nutrition_data,
                meal_data.get('confidence', 'medium')
            )

            await update.message.reply_text(response, reply_markup=reply_markup)

        except ValueError:
            await update.message.reply_text(
                "❌ Invalid input. Please enter a valid number (e.g., 1.5, 0.75, 2.0).\n"
                "Try again:"
            )

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
        portion_multiplier = nutrition_data.get('portion_multiplier', 1.0)

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

        # Add portion information
        portion_text = ""
        if portion_multiplier != 1.0:
            if portion_multiplier > 1.0:
                portion_text = f"\n🍽️ Estimated portion: {portion_multiplier}x (larger than standard)"
            else:
                portion_text = f"\n🍽️ Estimated portion: {portion_multiplier}x (smaller than standard)"
        else:
            portion_text = "\n🍽️ Portion: Standard serving"

        return (
            f"🍽️ {food_description}{portion_text}\n\n"
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

    async def _handle_request_reinstate(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle reinstatement request from revoked users."""
        if not query or not query.from_user:
            return

        user = query.from_user
        user_id = str(user.id)

        try:
            # Check if user was actually revoked
            existing_request = await self.firebase_service.get_access_request(user_id)

            if not existing_request or existing_request.get('status') != 'revoked':
                await query.edit_message_text(
                    "❌ **Error**\n\n"
                    "No revoked access record found for your account.\n"
                    "Please use the regular request access option."
                )
                return

            # Update status to reinstatement request
            access_request_ref = self.firebase_service.db.collection('access_requests').document(user_id)
            access_request_ref.update({
                'status': 'reinstate_request',
                'reinstate_requested_at': datetime.now(),
            })

            message = (
                "✅ **Reinstatement Request Submitted**\n\n"
                "Your request to restore access has been submitted for review.\n\n"
                "**What happens next:**\n"
                "• Your request will be reviewed by administrators\n"
                "• You'll be notified if your access is restored\n"
                "• Your previous data will be preserved\n\n"
                "**Note:** This is a reinstatement request for previously revoked access."
            )

            await query.edit_message_text(message, parse_mode='Markdown')

            # Log the reinstatement request
            logger.info(f"Reinstatement request submitted for user {user_id} ({user.first_name})")

        except Exception as e:
            logger.error(f"Error handling reinstatement request for user {user_id}: {e}")
            await query.edit_message_text(
                "❌ **Error**\n\n"
                "An error occurred while processing your reinstatement request. "
                "Please try again later."
            )

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
    """Set up the bot menu commands with different menus for admin and regular users."""

    # Regular user commands
    regular_commands = [
        BotCommand("start", "🚀 Start the bot"),
        BotCommand("summary", "📊 Today's nutrition summary"),
        BotCommand("history", "📝 View meal history"),
        BotCommand("help", "❓ Get help and instructions"),
        BotCommand("request_access", "🔑 Request access to use the bot"),
    ]

    # Admin commands (includes all regular commands plus admin-only)
    admin_commands = regular_commands + [
        BotCommand("admin_panel", "👑 Admin Control Panel"),
        BotCommand("list_requests", "📋 View access requests"),
        BotCommand("manage_users", "👥 Manage user access"),
        BotCommand("reload_access", "🔄 Reload access cache"),
    ]

    # Set commands for everyone (regular users will see regular menu)
    await application.bot.set_my_commands(regular_commands)
    logger.info("Bot menu commands set up successfully")

async def setup_admin_menu_for_user(application, user_id: str):
    """Set up admin menu for a specific admin user."""
    try:
        admin_commands = [
            BotCommand("start", "🚀 Start the bot"),
            BotCommand("summary", "📊 Today's nutrition summary"),
            BotCommand("history", "📝 View meal history"),
            BotCommand("help", "❓ Get help and instructions"),
            BotCommand("admin_panel", "👑 Admin Control Panel"),
            BotCommand("list_requests", "📋 View access requests"),
            BotCommand("manage_users", "👥 Manage user access"),
            BotCommand("reload_access", "🔄 Reload access cache"),
        ]

        # Set admin commands for specific user
        await application.bot.set_my_commands(admin_commands, scope={'type': 'chat', 'chat_id': user_id})
        logger.info(f"Admin menu set for user {user_id}")
    except Exception as e:
        logger.error(f"Error setting admin menu for user {user_id}: {e}")

def is_admin(user_id: str) -> bool:
    """Check if user is admin based on environment variable."""
    authorized_users_str = os.getenv('AUTHORIZED_TELEGRAM_IDS', '')
    if authorized_users_str:
        admin_ids = [uid.strip() for uid in authorized_users_str.split(',') if uid.strip()]
        return user_id in admin_ids
    return False

async def post_init(application):
    """Called after the application is initialized."""
    await setup_bot_menu(application)

    # Set up admin menu for admin users
    authorized_users_str = os.getenv('AUTHORIZED_TELEGRAM_IDS', '')
    if authorized_users_str:
        admin_ids = [uid.strip() for uid in authorized_users_str.split(',') if uid.strip()]
        for admin_id in admin_ids:
            await setup_admin_menu_for_user(application, admin_id)

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

    # Admin commands (new streamlined approach)
    application.add_handler(CommandHandler("admin_panel", jiak_ai.admin_panel_command))
    application.add_handler(CommandHandler("list_requests", jiak_ai.list_requests_command))
    application.add_handler(CommandHandler("manage_users", jiak_ai.manage_users_command))
    application.add_handler(CommandHandler("reload_access", jiak_ai.reload_access_command))

    application.add_handler(CallbackQueryHandler(jiak_ai.handle_callback))
    application.add_handler(MessageHandler(filters.PHOTO, jiak_ai.handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, jiak_ai.handle_text))
    
    logger.info("Starting JiakAI bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()