import functools
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .access_control import check_user_access, log_access_request

logger = logging.getLogger(__name__)

def require_access(func):
    """
    Decorator to require user authorization for bot commands.
    If user is not authorized, shows access request message.
    """
    @functools.wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        # Get user information
        if not update.effective_user:
            return
        
        user = update.effective_user
        user_id = str(user.id)
        
        # Check if user has access
        if check_user_access(user_id):
            # User is authorized, proceed with the command
            return await func(self, update, context, *args, **kwargs)
        
        # User is not authorized, show access request message
        await send_access_denied_message(update, context, user)
        
    return wrapper

def require_access_callback(func):
    """
    Decorator to require user authorization for callback query handlers.
    """
    @functools.wraps(func)
    async def wrapper(self, query, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        # Get user information from callback query
        if not query.from_user:
            return
        
        user = query.from_user
        user_id = str(user.id)
        
        # Check if user has access
        if check_user_access(user_id):
            # User is authorized, proceed with the callback
            return await func(self, query, context, *args, **kwargs)
        
        # User is not authorized, show access denied message
        await query.answer("❌ Access denied. Please request access first.", show_alert=True)
        
    return wrapper

async def send_access_denied_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    """
    Send access denied message with option to request access.
    
    Args:
        update: Telegram update object
        context: Bot context
        user: User object from Telegram
    """
    try:
        user_id = str(user.id)
        username = user.username
        first_name = user.first_name
        last_name = user.last_name
        
        # Create keyboard with request access button
        keyboard = [
            [InlineKeyboardButton("🔑 Request Access", callback_data="request_access")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        access_denied_message = (
            "🚫 **Access Restricted**\n\n"
            "This is an internal tool with limited access to manage costs and usage.\n\n"
            "**Why is access restricted?**\n"
            "• We limit access to authorized users to control expenses\n\n"
            "**How to get access:**\n"
            "If you're interested in using JiakAI, click the button below to request access. "
            "Your request will be reviewed and you'll be notified if approved.\n\n"
            "**Privacy Note:**\n"
            "When you request access, we collect your Telegram ID and username for identification purposes only."
        )
        
        if update.message:
            await update.message.reply_text(access_denied_message, reply_markup=reply_markup, parse_mode='Markdown')
        elif update.callback_query:
            await update.callback_query.edit_message_text(access_denied_message, reply_markup=reply_markup, parse_mode='Markdown')
        
        logger.info(f"Access denied for user {user_id} ({username})")
        
    except Exception as e:
        logger.error(f"Error sending access denied message: {e}")

async def handle_access_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle access request from unauthorized user.
    
    Args:
        update: Telegram update object
        context: Bot context
    """
    try:
        query = update.callback_query
        if not query or not query.from_user:
            return
        
        await query.answer()
        
        user = query.from_user
        user_id = str(user.id)
        username = user.username
        first_name = user.first_name
        last_name = user.last_name
        
        # Check if user is already authorized
        if check_user_access(user_id):
            await query.edit_message_text(
                "✅ You already have access to JiakAI!\n"
                "You can use all bot commands now. Try /start to begin."
            )
            return
        
        # Log the access request
        success = await log_access_request(user_id, username, first_name, last_name)
        
        if success:
            # Request logged successfully
            message = (
                "✅ **Access Request Submitted**\n\n"
                "Your request has been logged and will be reviewed by the administrators.\n\n"
                "**What happens next?**\n"
                "• Your request is now in the review queue\n"
                "• You'll be notified if your access is approved\n"
                "• Please be patient as reviews may take some time\n\n"
                "**Information Collected:**\n"
                f"• Telegram ID: `{user_id}`\n"
                f"• Username: @{username if username else 'N/A'}\n"
                f"• Name: {first_name or ''} {last_name or ''}".strip()
            )
        else:
            # Request already exists or failed
            message = (
                "ℹ️ **Request Already Exists**\n\n"
                "You have already submitted an access request.\n"
                "Please wait for administrator review.\n\n"
                "If you believe this is an error, please contact the administrator directly."
            )
        
        await query.edit_message_text(message, parse_mode='Markdown')
        
        logger.info(f"Access request processed for user {user_id} ({username})")
        
    except Exception as e:
        logger.error(f"Error handling access request: {e}")
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "❌ Error processing your request. Please try again later."
            )

def check_message_access(update: Update) -> bool:
    """
    Quick access check for message handlers.
    
    Args:
        update: Telegram update object
        
    Returns:
        True if user has access, False otherwise
    """
    if not update.effective_user:
        return False
    
    user_id = str(update.effective_user.id)
    return check_user_access(user_id)