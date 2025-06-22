import logging
from telegram import Update, ChatPermissions
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from telegram.error import BadRequest, InvalidToken
import json
import os
import asyncio
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TopicKeywordBot:
    def __init__(self, token):
        self.token = token.strip()  # Remove any whitespace
        self.app = Application.builder().token(self.token).build()
        self.setup_handlers()
        self.config_file = "bot_config.json"
        self.load_config()

    def load_config(self):
        try:
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.config = {
                "topic_keywords": {},
                "admin_users": [],
                "muted_users": {}  # Store muted users with unmute timestamps
            }
            self.save_config()

    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)

    def setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("add_keyword", self.add_keyword_command))
        self.app.add_handler(CommandHandler("remove_keyword", self.remove_keyword_command))
        self.app.add_handler(CommandHandler("list_keywords", self.list_keywords_command))
        self.app.add_handler(CommandHandler("add_admin", self.add_admin_command))
        self.app.add_handler(CommandHandler("forceaddadmin", self.force_add_admin_command))
        self.app.add_handler(CommandHandler("list_admins", self.list_admins_command))
        self.app.add_handler(CommandHandler("remove_admin", self.remove_admin_command))
        self.app.add_handler(CommandHandler("unmute", self.unmute_command))
        self.app.add_handler(CommandHandler("check_mutes", self.check_mutes_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.filter_message))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 <b>Topic Keyword Filter Bot</b>\n\n"
            "I can delete messages containing specific keywords and mute users in designated topics!\n\n"
            "Use /help to see available commands.",
            parse_mode="HTML"
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
🤖 <b>Topic Keyword Filter Bot Commands:</b>

<b>For Admins:</b>
• /add_keyword &lt;topic_id&gt; &lt;keyword&gt; - Add a keyword to filter (use 0 for general chat)
• /remove_keyword &lt;topic_id&gt; &lt;keyword&gt; - Remove a keyword (use 0 for general chat)
• /list_keywords [topic_id] - List keywords (all or specific topic/chat)
• /add_admin &lt;user_id&gt; - Add a user as bot admin
• /forceaddadmin &lt;user_id&gt; - Forcefully add admin (restricted access)
• /list_admins - Show all bot admins
• /remove_admin &lt;user_id&gt; - Remove admin
• /unmute &lt;user_id&gt; - Manually unmute a user
• /check_mutes - Check currently muted users

<b>Features:</b>
• Regular users get muted for 6 hours when using filtered keywords
• Bot admins only get their messages deleted (no mute)
• Automatic unmuting after 6 hours

<b>Notes:</b>
• Bot must be admin with delete and restrict permissions
• Keywords are case-insensitive
• Use topic_id 0 for general chat, actual topic ID for topics
• Get topic ID from Telegram topic URL
        """
        await update.message.reply_text(help_text, parse_mode="HTML")

    async def is_telegram_admin(self, user_id: int, chat_id: int) -> bool:
        """Check if user is a Telegram chat admin"""
        try:
            chat_member = await self.app.bot.get_chat_member(chat_id, user_id)
            return chat_member.status in ['administrator', 'creator']
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            return False

    def is_bot_admin(self, user_id: int) -> bool:
        """Check if user is a bot admin"""
        return user_id in self.config.get("admin_users", [])

    async def add_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_bot_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot admins can configure keyword filters.")
            return

        if len(context.args) < 2:
            await update.message.reply_text("❌ Usage: /add_keyword <topic_id> <keyword>\nUse topic_id 0 for general chat, or actual topic ID for topics")
            return

        try:
            topic_id = int(context.args[0])
            keyword = " ".join(context.args[1:]).lower()
            chat_id = str(update.effective_chat.id)

            self.config["topic_keywords"].setdefault(chat_id, {})
            self.config["topic_keywords"][chat_id].setdefault(str(topic_id), [])

            if keyword not in self.config["topic_keywords"][chat_id][str(topic_id)]:
                self.config["topic_keywords"][chat_id][str(topic_id)].append(keyword)
                self.save_config()
                
                location = "general chat" if topic_id == 0 else f"topic {topic_id}"
                await update.message.reply_text(f"✅ Added keyword '{keyword}' to {location}.")
            else:
                await update.message.reply_text(f"⚠️ Keyword '{keyword}' already exists.")
        except ValueError:
            await update.message.reply_text("❌ Topic ID must be a number.")

    async def remove_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_bot_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot admins can configure keyword filters.")
            return

        if len(context.args) < 2:
            await update.message.reply_text("❌ Usage: /remove_keyword <topic_id> <keyword>\nUse topic_id 0 for general chat, or actual topic ID for topics")
            return

        try:
            topic_id = int(context.args[0])
            keyword = " ".join(context.args[1:]).lower()
            chat_id = str(update.effective_chat.id)

            if (chat_id in self.config["topic_keywords"] and 
                str(topic_id) in self.config["topic_keywords"][chat_id] and
                keyword in self.config["topic_keywords"][chat_id][str(topic_id)]):
                
                self.config["topic_keywords"][chat_id][str(topic_id)].remove(keyword)
                self.save_config()
                
                location = "general chat" if topic_id == 0 else f"topic {topic_id}"
                await update.message.reply_text(f"✅ Removed keyword '{keyword}' from {location}.")
            else:
                location = "general chat" if topic_id == 0 else f"topic {topic_id}"
                await update.message.reply_text(f"❌ Keyword '{keyword}' not found in {location}.")
        except ValueError:
            await update.message.reply_text("❌ Topic ID must be a number.")

    async def list_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_bot_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot admins can view keyword lists.")
            return

        chat_id = str(update.effective_chat.id)
        
        if not self.config["topic_keywords"].get(chat_id):
            await update.message.reply_text("❌ No keywords configured for this chat.")
            return

        if context.args:
            try:
                topic_id = str(int(context.args[0]))
                keywords = self.config["topic_keywords"][chat_id].get(topic_id, [])
                if keywords:
                    keyword_list = "\n".join([f"• {kw}" for kw in keywords])
                    await update.message.reply_text(f"🔍 <b>Keywords for topic {topic_id}:</b>\n{keyword_list}", parse_mode="HTML")
                else:
                    await update.message.reply_text(f"❌ No keywords found for topic {topic_id}.")
            except ValueError:
                await update.message.reply_text("❌ Topic ID must be a number.")
        else:
            response = "🔍 <b>All Keywords:</b>\n\n"
            for topic_id, keywords in self.config["topic_keywords"][chat_id].items():
                if keywords:
                    keyword_list = ", ".join(keywords)
                    location = "General Chat" if topic_id == "0" else f"Topic {topic_id}"
                    response += f"<b>{location}:</b> {keyword_list}\n"
            
            if response == "🔍 <b>All Keywords:</b>\n\n":
                response = "❌ No keywords configured."
            
            await update.message.reply_text(response, parse_mode="HTML")

    async def add_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_bot_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only existing bot admins can add new admins.")
            return

        if not context.args:
            await update.message.reply_text("❌ Usage: /add_admin <user_id>")
            return

        try:
            user_id = int(context.args[0])
            if user_id not in self.config["admin_users"]:
                self.config["admin_users"].append(user_id)
                self.save_config()
                await update.message.reply_text(f"✅ Added user {user_id} as bot admin.")
            else:
                await update.message.reply_text(f"⚠️ User {user_id} is already a bot admin.")
        except ValueError:
            await update.message.reply_text("❌ User ID must be a number.")

    async def force_add_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Only allow specific user ID to use this command
        if update.effective_user.id != 5199331612:
            await update.message.reply_text("❌ You are not authorized to use this command.")
            return

        if not context.args:
            await update.message.reply_text("❌ Usage: /forceaddadmin <user_id>")
            return

        try:
            user_id = int(context.args[0])
            if user_id not in self.config["admin_users"]:
                self.config["admin_users"].append(user_id)
                self.save_config()
                await update.message.reply_text(f"✅ Force added user {user_id} as bot admin.")
            else:
                await update.message.reply_text(f"⚠️ User {user_id} is already a bot admin.")
        except ValueError:
            await update.message.reply_text("❌ User ID must be a number.")

    async def list_admins_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_bot_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot admins can view admin list.")
            return

        admins = self.config.get("admin_users", [])
        if admins:
            admin_list = "\n".join([f"• {admin_id}" for admin_id in admins])
            await update.message.reply_text(f"👥 <b>Bot Admins:</b>\n{admin_list}", parse_mode="HTML")
        else:
            await update.message.reply_text("❌ No bot admins configured.")

    async def remove_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_bot_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot admins can remove other admins.")
            return

        if not context.args:
            await update.message.reply_text("❌ Usage: /remove_admin <user_id>")
            return

        try:
            user_id = int(context.args[0])
            if user_id in self.config["admin_users"]:
                self.config["admin_users"].remove(user_id)
                self.save_config()
                await update.message.reply_text(f"✅ Removed user {user_id} from bot admins.")
            else:
                await update.message.reply_text(f"❌ User {user_id} is not a bot admin.")
        except ValueError:
            await update.message.reply_text("❌ User ID must be a number.")

    async def unmute_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_bot_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot admins can unmute users.")
            return

        if not context.args:
            await update.message.reply_text("❌ Usage: /unmute <user_id>")
            return

        try:
            user_id = int(context.args[0])
            chat_id = str(update.effective_chat.id)
            
            # Remove from muted users config
            mute_key = f"{chat_id}_{user_id}"
            if mute_key in self.config.get("muted_users", {}):
                del self.config["muted_users"][mute_key]
                self.save_config()
            
            # Restore permissions
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_change_info=False,
                    can_invite_users=False,
                    can_pin_messages=False
                )
            )
            
            await update.message.reply_text(f"✅ User {user_id} has been unmuted.")
            
        except ValueError:
            await update.message.reply_text("❌ User ID must be a number.")
        except BadRequest as e:
            await update.message.reply_text(f"❌ Failed to unmute user: {e}")

    async def check_mutes_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_bot_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot admins can check muted users.")
            return

        chat_id = str(update.effective_chat.id)
        current_time = datetime.now()
        
        # Clean up expired mutes
        expired_mutes = []
        for mute_key, unmute_time_str in self.config.get("muted_users", {}).items():
            if mute_key.startswith(f"{chat_id}_"):
                unmute_time = datetime.fromisoformat(unmute_time_str)
                if current_time >= unmute_time:
                    expired_mutes.append(mute_key)
        
        # Remove expired mutes
        for mute_key in expired_mutes:
            del self.config["muted_users"][mute_key]
        
        if expired_mutes:
            self.save_config()
        
        # Show current mutes
        active_mutes = []
        for mute_key, unmute_time_str in self.config.get("muted_users", {}).items():
            if mute_key.startswith(f"{chat_id}_"):
                user_id = mute_key.split("_")[1]
                unmute_time = datetime.fromisoformat(unmute_time_str)
                time_left = unmute_time - current_time
                
                if time_left.total_seconds() > 0:
                    hours = int(time_left.total_seconds() // 3600)
                    minutes = int((time_left.total_seconds() % 3600) // 60)
                    active_mutes.append(f"• User {user_id}: {hours}h {minutes}m remaining")
        
        if active_mutes:
            mute_list = "\n".join(active_mutes)
            await update.message.reply_text(f"🔇 <b>Currently Muted Users:</b>\n{mute_list}", parse_mode="HTML")
        else:
            await update.message.reply_text("✅ No users are currently muted.")

    async def mute_user(self, chat_id: int, user_id: int, keyword: str, context: ContextTypes.DEFAULT_TYPE):
        """Mute a user for 6 hours"""
        try:
            # Mute the user
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_polls=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False,
                    can_change_info=False,
                    can_invite_users=False,
                    can_pin_messages=False
                ),
                until_date=datetime.now() + timedelta(hours=6)
            )
            
            # Store mute info
            mute_key = f"{chat_id}_{user_id}"
            unmute_time = datetime.now() + timedelta(hours=6)
            self.config.setdefault("muted_users", {})[mute_key] = unmute_time.isoformat()
            self.save_config()
            
            # Send notification with user mention
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔇 <a href='tg://user?id={user_id}'>User</a> has been muted for 6 hours for using \"{keyword}\" in this topic.",
                parse_mode="HTML"
            )
            
            logger.info(f"Muted user {user_id} for keyword '{keyword}' until {unmute_time}")
            
        except BadRequest as e:
            logger.error(f"Failed to mute user {user_id}: {e}")

    async def filter_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return

        chat_id = str(update.effective_chat.id)
        message_thread_id = update.message.message_thread_id
        user_id = update.effective_user.id
        
        # Determine the topic ID (0 for general chat, actual ID for topics)
        topic_id = "0" if message_thread_id is None else str(message_thread_id)
        
        # Check if this topic/chat has keywords to filter
        topic_keywords = self.config["topic_keywords"].get(chat_id, {}).get(topic_id, [])
        
        if not topic_keywords:
            return  # No keywords configured for this topic/chat

        message_text = update.message.text.lower()
        
        # Check if message contains any filtered keywords
        for keyword in topic_keywords:
            if keyword in message_text:
                try:
                    # Always delete the message
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=update.message.message_id
                    )
                    
                    # Check if user is bot admin or telegram admin
                    is_bot_admin = self.is_bot_admin(user_id)
                    is_tg_admin = await self.is_telegram_admin(user_id, update.effective_chat.id)
                    
                    location = "general chat" if topic_id == "0" else f"topic {topic_id}"
                    
                    if is_bot_admin or is_tg_admin:
                        # Only delete message for admins, no mute
                        logger.info(f"Deleted admin message containing keyword '{keyword}' in {location}")
                    else:
                        # Mute regular users
                        await self.mute_user(update.effective_chat.id, user_id, keyword, context)
                        logger.info(f"Deleted and muted user {user_id} for keyword '{keyword}' in {location}")
                    
                    return
                    
                except BadRequest as e:
                    logger.error(f"Failed to delete message: {e}")
                    return

    async def test_token(self):
        """Test if the bot token is valid"""
        try:
            bot_info = await self.app.bot.get_me()
            logger.info(f"Bot token is valid. Bot name: {bot_info.first_name}")
            return True
        except InvalidToken:
            logger.error("Invalid bot token!")
            return False
        except Exception as e:
            logger.error(f"Error testing token: {e}")
            return False

    def run(self):
        """Run the bot with proper error handling"""
        try:
            print("🚀 Starting bot...")
            self.app.run_polling(drop_pending_updates=True)
            
        except InvalidToken:
            print("❌ Invalid bot token! Please check your token.")
        except Exception as e:
            logger.error(f"Error running bot: {e}")
            print(f"❌ Error running bot: {e}")

def main():
    # Get token from environment variable or input
    token = os.getenv('BOT_TOKEN')
    
    if not token:
        token = input("Please enter your bot token: ").strip()
    
    if not token:
        print("❌ No bot token provided!")
        return
    
    # Validate token format
    if ':' not in token:
        print("❌ Invalid token format! Token should be in format: 'XXXXXXXXX:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX'")
        return
    
    bot = TopicKeywordBot(token)
    bot.run()

if __name__ == "__main__":
    main()
