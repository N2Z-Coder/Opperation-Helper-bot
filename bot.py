
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
AGNES_API_KEY = os.getenv("AGNES_API_KEY")

import os
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("🖼️ AI Image", callback_data="image"),
            InlineKeyboardButton("🎬 AI Video", callback_data="video")
        ],
        [
            InlineKeyboardButton("ℹ️ Help", callback_data="help")
        ]
    ]

    await update.message.reply_text(
        "🤖 Welcome to AI Image & Video Bot!\n\n"
        "Choose a service below:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    if query.data == "image":
        context.user_data["mode"] = "image"
        await query.message.reply_text(
            "🖼️ Send your image prompt:"
        )

    elif query.data == "video":
        context.user_data["mode"] = "video"
        await query.message.reply_text(
            "🎬 Send your video prompt:"
        )

    elif query.data == "help":
        await query.message.reply_text(
            "Use /start to open the main menu.\n"
            "Use /cancel to cancel a request."
        )

async def prompt_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    mode = context.user_data.get("mode")

    if not mode:
        await update.message.reply_text(
            "Please choose Image or Video using /start."
        )
        return

    prompt = update.message.text

    context.user_data["mode"] = None

    await update.message.reply_text(
        f"✅ {mode.upper()} prompt received!\n\n"
        f"Prompt: {prompt}\n\n"
        "⏳ AI generation API will be connected in the next step."
    )

async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data["mode"] = None
    await update.message.reply_text("❌ Request cancelled.")

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"AI Bot is running!")

    def log_message(self, format, *args):
        pass

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is missing!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, prompt_handler)
    )

    
print("AI Bot is running...")

threading.Thread(
    target=run_web_server,
    daemon=True
).start()

app.run_polling()


if __name__ == "__main__":
    main()
