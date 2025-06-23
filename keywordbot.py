import logging
from telegram import Update, ChatPermissions
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from telegram.error import BadRequest, InvalidToken, Forbidden
import json
import os
import asyncio
from datetime import datetime, timedelta

# Configure logging with more detailed output
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

class TopicKeywordBot:
    def __init__(self, token):
        self.token = token.strip()
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
                "muted_users": {}
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
        self.app.add_handler(CommandHandler("debug", self.debug_command))
        self.app.add_handler(CommandHandler("test_permissions", self.test_permissions_command))
        # Message filter handler - highest priority
        self.app.add_handler(MessageHandler(filters.TEXT, self.filter_message), group=0)

    async def test_permissions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Test bot permissions in current chat"""
        if not self.is_bot_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot admins can test permissions.")
            return

        try:
            bot_member = await context.bot.get_chat_member(update.effective_chat.id, context.bot.id)
            
            permissions_text = f"""
🔍 <b>Bot Permissions Test:</b>

<b>Status:</b> {bot_member.status}
<b>Can Restrict Members:</b> {getattr(bot_member, 'can_restrict_members', 'Unknown')}
<b>Can Manage Topics:</b> {getattr(bot_member, 'can_manage_topics', 'Unknown')}

<b>Chat Type:</b> {update.effective_chat.type}
<b>Chat ID:</b> {update.effective_chat.id}
<b>Thread ID:</b> {update.message.message_thread_id or 'None (General chat)'}
            """
            
            await update.message.reply_text(permissions_text, parse_mode="HTML")
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error checking permissions: {e}")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 <b>Topic Keyword Filter Bot</b>\n\n"
            "I can mute users for using specific keywords in designated topics!\n\n"
            "Use /help to see available commands.",
            parse_mode="HTML"
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
🤖 <b>Topic Keyword Filter Bot Commands:</b>

<b>For Admins:</b>
• /add_keyword &lt;topic_id&gt; &lt;keyword&gt; - Add a keyword to filter
• /remove_keyword &lt;topic_id&gt; &lt;keyword&gt; - Remove a keyword
• /list_keywords [topic_id] - List keywords (all or specific topic/chat)
• /add_admin &lt;user_id&gt; - Add a user as bot admin
• /forceaddadmin &lt;user_id&gt; - Forcefully add admin (restricted access)
• /list_admins - Show all bot admins
• /remove_admin &lt;user_id&gt; - Remove admin
• /unmute &lt;user_id&gt; - Manually unmute a user
• /check_mutes - Check currently muted users
• /debug - Show debug information about current chat
• /test_permissions - Test bot permissions

<b>Features:</b>
• Regular users get muted for 12 hours when using filtered keywords
• Bot admins: no restrictions applied
• Telegram admins: no restrictions applied
• Automatic unmuting after 12 hours

<b>Notes:</b>
• Bot must be admin with restrict permissions
• Keywords are case-insensitive
• For supergroups with topics: use topic ID from URL or /debug
• For general chat in supergroups: often topic ID 1 or use /debug to confirm
        """
        await update.message.reply_text(help_text, parse_mode="HTML")

    async def debug_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Debug command to show current chat information"""
        if not self.is_bot_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot admins can use debug command.")
            return

        chat_id = str(update.effective_chat.id)
        message_thread_id = update.message.message_thread_id
        
        # For supergroups, general chat usually has thread_id = 1, not None
        if update.effective_chat.type == 'supergroup':
            topic_id = str(message_thread_id) if message_thread_id else "1"
        else:
            topic_id = "0" if message_thread_id is None else str(message_thread_id)
        
        # Check bot permissions
        try:
            bot_member = await context.bot.get_chat_member(update.effective_chat.id, context.bot.id)
            can_restrict = getattr(bot_member, 'can_restrict_members', False)
            bot_status = bot_member.status
        except Exception as e:
            can_restrict = "Error checking"
            bot_status = "Unknown"
            logger.error(f"Error checking bot permissions: {e}")

        debug_info = f"""
🔍 <b>Debug Information:</b>

<b>Chat Info:</b>
• Chat Type: {update.effective_chat.type}
• Chat ID: {chat_id}
• Raw Thread ID: {message_thread_id}
• Detected Topic ID: {topic_id}

<b>Bot Status:</b>
• Status: {bot_status}
• Can Restrict Users: {can_restrict}

<b>Keywords for this location:</b>
        """
        
        topic_keywords = self.config["topic_keywords"].get(chat_id, {}).get(topic_id, [])
        if topic_keywords:
            keyword_list = "\n".join([f"• {kw}" for kw in topic_keywords])
            debug_info += f"\n{keyword_list}"
        else:
            debug_info += "\n• No keywords configured"

        debug_info += f"\n\n<b>Your User ID:</b> {update.effective_user.id}"
        debug_info += f"\n<b>Are you bot admin?:</b> {self.is_bot_admin(update.effective_user.id)}"
        
        await update.message.reply_text(debug_info, parse_mode="HTML")

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
            await update.message.reply_text("❌ Usage: /add_keyword <topic_id> <keyword>\nUse /debug to find the correct topic ID")
            return

        try:
            topic_id = context.args[0]
keywords = [kw.lower() for kw in context.args[1:]]
chat_id = str(update.effective_chat.id)

self.config["topic_keywords"].setdefault(chat_id, {})
self.config["topic_keywords"][chat_id].setdefault(topic_id, [])

added = []
skipped = []

for kw in keywords:
    if kw not in self.config["topic_keywords"][chat_id][topic_id]:
        self.config["topic_keywords"][chat_id][topic_id].append(kw)
        added.append(kw)
    else:
        skipped.append(kw)

self.save_config()

response = ""
if added:
    response += f"✅ Added: {', '.join(added)}\n"
if skipped:
    response += f"⚠️ Already existed: {', '.join(skipped)}"
await update.message.reply_text(response.strip())

        except Exception as e:
            await update.message.reply_text(f"❌ Error adding keyword: {e}")

    async def remove_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_bot_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot admins can configure keyword filters.")
            return

        if len(context.args) < 2:
            await update.message.reply_text("❌ Usage: /remove_keyword <topic_id> <keyword>")
            return

        try:
            topic_id = context.args[0]
            keyword = " ".join(context.args[1:]).lower()
            chat_id = str(update.effective_chat.id)

            if (chat_id in self.config["topic_keywords"] and 
                topic_id in self.config["topic_keywords"][chat_id] and
                keyword in self.config["topic_keywords"][chat_id][topic_id]):
                
                self.config["topic_keywords"][chat_id][topic_id].remove(keyword)
                self.save_config()
                await update.message.reply_text(f"✅ Removed keyword '{keyword}' from topic {topic_id}.")
            else:
                await update.message.reply_text(f"❌ Keyword '{keyword}' not found in topic {topic_id}.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error removing keyword: {e}")

    async def list_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_bot_admin(update.effective_user.id):
            await update.message.reply_text("❌ Only bot admins can view keyword lists.")
            return

        chat_id = str(update.effective_chat.id)
        
        if not self.config["topic_keywords"].get(chat_id):
            await update.message.reply_text("❌ No keywords configured for this chat.")
            return

        if context.args:
            topic_id = context.args[0]
            keywords = self.config["topic_keywords"][chat_id].get(topic_id, [])
            if keywords:
                keyword_list = "\n".join([f"• {kw}" for kw in keywords])
                await update.message.reply_text(f"🔍 <b>Keywords for topic {topic_id}:</b>\n{keyword_list}", parse_mode="HTML")
            else:
                await update.message.reply_text(f"❌ No keywords found for topic {topic_id}.")
        else:
            response = "🔍 <b>All Keywords:</b>\n\n"
            for topic_id, keywords in self.config["topic_keywords"][chat_id].items():
                if keywords:
                    keyword_list = ", ".join(keywords)
                    response += f"<b>Topic {topic_id}:</b> {keyword_list}\n"
            
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
            
            # Restore full permissions
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_change_info=True,
                    can_invite_users=True,
                    can_pin_messages=True,
                    can_manage_topics=True
                )
            )
            
            await update.message.reply_text(f"✅ User {user_id} has been unmuted.")
            
        except ValueError:
            await update.message.reply_text("❌ User ID must be a number.")
        except (BadRequest, Forbidden) as e:
            await update.message.reply_text(f"❌ Failed to unmute user: {e}")
            logger.error(f"Failed to unmute user {user_id}: {e}")

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
        
        # Remove expired mutes and auto-unmute
        for mute_key in expired_mutes:
            user_id = int(mute_key.split("_")[1])
            try:
                await context.bot.restrict_chat_member(
                    chat_id=update.effective_chat.id,
                    user_id=user_id,
                    permissions=ChatPermissions(
                        can_send_messages=True,
                        can_send_media_messages=True,
                        can_send_polls=True,
                        can_send_other_messages=True,
                        can_add_web_page_previews=True,
                        can_change_info=True,
                        can_invite_users=True,
                        can_pin_messages=True,
                        can_manage_topics=True
                    )
                )
                logger.info(f"Auto-unmuted expired mute for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to auto-unmute user {user_id}: {e}")
            
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
        """Mute a user for 12 hours"""
        try:
            # Calculate unmute time (12 hours)
            unmute_time = datetime.now() + timedelta(hours=12)
            
            # Mute the user with restricted permissions
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
                    can_pin_messages=False,
                    can_manage_topics=False
                ),
                until_date=unmute_time
            )
            
            # Store mute info
            mute_key = f"{chat_id}_{user_id}"
            self.config.setdefault("muted_users", {})[mute_key] = unmute_time.isoformat()
            self.save_config()
            
            # Send notification with user mention
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔇 User <a href='tg://user?id={user_id}'>{user_id}</a> was muted for 12 hours for using a restricted keyword in this topic.",
                parse_mode="HTML"
            )
            
            logger.info(f"Successfully muted user {user_id} for keyword '{keyword}' until {unmute_time}")
            
        except (BadRequest, Forbidden) as e:
            logger.error(f"Failed to mute user {user_id}: {e}")
            # Try to send a notification about the failed mute
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ Could not mute user <a href='tg://user?id={user_id}'>{user_id}</a> due to insufficient permissions. Please ensure bot has 'Restrict Members' permission.",
                    parse_mode="HTML"
                )
            except:
                pass

    async def filter_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return

        chat_id = str(update.effective_chat.id)
        message_thread_id = update.message.message_thread_id
        user_id = update.effective_user.id
        
        # Determine the topic ID based on chat type
        if update.effective_chat.type == 'supergroup':
            topic_id = str(message_thread_id) if message_thread_id else "1"
        else:
            topic_id = "0" if message_thread_id is None else str(message_thread_id)
        
        logger.debug(f"Processing message in chat {chat_id} (type: {update.effective_chat.type}), topic {topic_id}, from user {user_id}")
        
        # Check if this topic/chat has keywords to filter
        topic_keywords = self.config["topic_keywords"].get(chat_id, {}).get(topic_id, [])
        
        if not topic_keywords:
            return

        message_text = update.message.text.lower()
        
        # Check if message contains any filtered keywords
        for keyword in topic_keywords:
            if keyword in message_text:
                logger.info(f"Keyword '{keyword}' found in message from user {user_id}")
                
                # Check if user is bot admin or telegram admin
                is_bot_admin = self.is_bot_admin(user_id)
                is_tg_admin = await self.is_telegram_admin(user_id, update.effective_chat.id)
                
                if is_bot_admin or is_tg_admin:
                    # Bot admins and Telegram admins: no restrictions applied
                    logger.info(f"Admin {user_id} used prohibited keyword '{keyword}' - no action taken")
                    return
                else:
                    # Regular users: just mute (don't delete message)
                    await self.mute_user(update.effective_chat.id, user_id, keyword, context)
                    logger.info(f"Regular user {user_id} muted for keyword '{keyword}'")
                    # Delete the triggering message
try:
    await context.bot.delete_message(
        chat_id=update.effective_chat.id,
        message_id=update.message.message_id
    )
except Exception as e:
    logger.warning(f"Could not delete original message: {e}")

# Attempt to delete replies to that message
try:
    async for msg in context.bot.get_chat_history(chat_id=update.effective_chat.id, limit=100):
        if msg.reply_to_message and msg.reply_to_message.message_id == update.message.message_id:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg.message_id)
            except Exception as e:
                logger.warning(f"Failed to delete reply message {msg.message_id}: {e}")
except Exception as e:
    logger.warning(f"Could not fetch chat history to delete replies: {e}")

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
            # Test token before running
            asyncio.get_event_loop().run_until_complete(self.test_token())
            
            # Clear any pending updates and conflicts
            print("🔄 Clearing pending updates...")
            self.app.run_polling(
                drop_pending_updates=True,
                close_loop=False,
                stop_signals=None
            )
            
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
        print("❌ No bot token provided! Exiting...")
        return
    
    try:
        bot = TopicKeywordBot(token)
        bot.run()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logger.error(f"Unexpected error in main: {e}")

if __name__ == "__main__":
    main()
