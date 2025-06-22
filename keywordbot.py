import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from telegram.error import BadRequest, InvalidToken
import json
import os
import asyncio

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
                "admin_users": []
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
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.filter_message))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 <b>Topic Keyword Filter Bot</b>\n\n"
            "I can delete messages containing specific keywords, but only in designated topics!\n\n"
            "Use /help to see available commands.",
            parse_mode="HTML"
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
🤖 <b>Topic Keyword Filter Bot Commands:</b>

<b>For Admins:</b>
• /add_keyword &lt;topic_id&gt; &lt;keyword&gt; - Add a keyword to filter in a topic
• /remove_keyword &lt;topic_id&gt; &lt;keyword&gt; - Remove a keyword from a topic
• /list_keywords [topic_id] - List keywords (all or specific topic)
• /add_admin &lt;user_id&gt; - Add a user as bot admin
• /forceaddadmin &lt;user_id&gt; - Forcefully add admin (no permission needed)
• /list_admins - Show all bot admins
• /remove_admin &lt;user_id&gt; - Remove admin

<b>Notes:</b>
• Bot must be admin with delete permissions
• Keywords are case-insensitive
• Use topic_id from Telegram topic URL
        """
        await update.message.reply_text(help_text, parse_mode="HTML")

    def is_admin(self, user_id: int, chat_id: int) -> bool:
        return user_id in self.config.get("admin_users", [])

    async def add_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id, update.effective_chat.id):
            await update.message.reply_text("❌ Only admins can configure keyword filters.")
            return

        if len(context.args) < 2:
            await update.message.reply_text("❌ Usage: /add_keyword <topic_id> <keyword>")
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
                await update.message.reply_text(f"✅ Added keyword '{keyword}' to topic {topic_id}.")
            else:
                await update.message.reply_text(f"⚠️ Keyword '{keyword}' already exists.")
        except ValueError:
            await update.message.reply_text("❌ Topic ID must be a number.")

    async def remove_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id, update.effective_chat.id):
            await update.message.reply_text("❌ Only admins can configure keyword filters.")
            return

        if len(context.args) < 2:
            await update.message.reply_text("❌ Usage: /remove_keyword <topic_id> <keyword>")
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
                await update.message.reply_text(f"✅ Removed keyword '{keyword}' from topic {topic_id}.")
            else:
                await update.message.reply_text(f"❌ Keyword '{keyword}' not found in topic {topic_id}.")
        except ValueError:
            await update.message.reply_text("❌ Topic ID must be a number.")

    async def list_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id, update.effective_chat.id):
            await update.message.reply_text("❌ Only admins can view keyword lists.")
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
                    response += f"<b>Topic {topic_id}:</b> {keyword_list}\n"
            
            if response == "🔍 <b>All Keywords:</b>\n\n":
                response = "❌ No keywords configured."
            
            await update.message.reply_text(response, parse_mode="HTML")

    async def add_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id, update.effective_chat.id):
            await update.message.reply_text("❌ Only existing admins can add new admins.")
            return

        if not context.args:
            await update.message.reply_text("❌ Usage: /add_admin <user_id>")
            return

        try:
            user_id = int(context.args[0])
            if user_id not in self.config["admin_users"]:
                self.config["admin_users"].append(user_id)
                self.save_config()
                await update.message.reply_text(f"✅ Added user {user_id} as admin.")
            else:
                await update.message.reply_text(f"⚠️ User {user_id} is already an admin.")
        except ValueError:
            await update.message.reply_text("❌ User ID must be a number.")

    async def force_add_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ Usage: /forceaddadmin <user_id>")
            return

        try:
            user_id = int(context.args[0])
            if user_id not in self.config["admin_users"]:
                self.config["admin_users"].append(user_id)
                self.save_config()
                await update.message.reply_text(f"✅ Force added user {user_id} as admin.")
            else:
                await update.message.reply_text(f"⚠️ User {user_id} is already an admin.")
        except ValueError:
            await update.message.reply_text("❌ User ID must be a number.")

    async def list_admins_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id, update.effective_chat.id):
            await update.message.reply_text("❌ Only admins can view admin list.")
            return

        admins = self.config.get("admin_users", [])
        if admins:
            admin_list = "\n".join([f"• {admin_id}" for admin_id in admins])
            await update.message.reply_text(f"👥 <b>Bot Admins:</b>\n{admin_list}", parse_mode="HTML")
        else:
            await update.message.reply_text("❌ No admins configured.")

    async def remove_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_admin(update.effective_user.id, update.effective_chat.id):
            await update.message.reply_text("❌ Only admins can remove other admins.")
            return

        if not context.args:
            await update.message.reply_text("❌ Usage: /remove_admin <user_id>")
            return

        try:
            user_id = int(context.args[0])
            if user_id in self.config["admin_users"]:
                self.config["admin_users"].remove(user_id)
                self.save_config()
                await update.message.reply_text(f"✅ Removed user {user_id} from admins.")
            else:
                await update.message.reply_text(f"❌ User {user_id} is not an admin.")
        except ValueError:
            await update.message.reply_text("❌ User ID must be a number.")

    async def filter_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return

        chat_id = str(update.effective_chat.id)
        message_thread_id = update.message.message_thread_id
        
        if not message_thread_id:
            return  # Not in a topic

        # Check if this topic has keywords to filter
        topic_keywords = self.config["topic_keywords"].get(chat_id, {}).get(str(message_thread_id), [])
        
        if not topic_keywords:
            return  # No keywords configured for this topic

        message_text = update.message.text.lower()
        
        # Check if message contains any filtered keywords
        for keyword in topic_keywords:
            if keyword in message_text:
                try:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=update.message.message_id
                    )
                    logger.info(f"Deleted message containing keyword '{keyword}' in topic {message_thread_id}")
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