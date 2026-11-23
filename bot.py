
import os
import asyncio
import threading
import base64
import httpx

from http.server import BaseHTTPRequestHandler, HTTPServer
from openai import OpenAI
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
AGNES_API_KEY = os.getenv("AGNES_API_KEY")

client = OpenAI(
    api_key=AGNES_API_KEY or "missing-key",
    base_url="https://apihub.agnes-ai.com/v1"
)

VIDEO_MODEL = "agnes-video-2.5-flash"
VIDEO_API = "https://apihub.agnes-ai.com"


# Render Health Check
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


# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    keyboard = [
        [
            InlineKeyboardButton(" AI Image", callback_data="image"),
            InlineKeyboardButton(" AI Video", callback_data="video"),
        ],
        [
            InlineKeyboardButton(" Help", callback_data="help")
        ],
    ]

    await update.message.reply_text(
        "Welcome to AI Image & Video Bot!\n\n"
        "Choose a service below:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# Button handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "image":
        context.user_data["mode"] = "image"
        await query.message.reply_text(
            " Send your image prompt:"
        )

    elif query.data == "video":
        keyboard = [
            [
                InlineKeyboardButton(
                    " Text to Video",
                    callback_data="video_text"
                )
            ],
            [
                InlineKeyboardButton(
                    " Image to Video",
                    callback_data="video_image"
                )
            ],
        ]

        await query.message.reply_text(
            " Choose Video Generation Mode:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif query.data == "video_text":
        context.user_data["mode"] = "video_text"
        await query.message.reply_text(
            " Send your video prompt:\n\n"
            "Example: A beautiful butterfly flying in a flower garden, cinematic camera movement."
        )

    elif query.data == "video_image":
        context.user_data["mode"] = "video_image_photo"
        context.user_data.pop("video_first_frame", None)
        await query.message.reply_text(
            " Please send the image you want to animate."
        )

    elif query.data == "help":
        await query.message.reply_text(
            "How to use:\n\n"
            "1. Choose AI Image to generate an image.\n"
            "2. Choose AI Video for Text-to-Video or Image-to-Video.\n"
            "3. Use /cancel to cancel a request.\n"
            "4. Use /start to open the menu again."
        )


# Image upload handler for Image-to-Video
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")

    if mode != "video_image_photo":
        await update.message.reply_text(
            "Please choose Image-to-Video from /start first."
        )
        return

    if not AGNES_API_KEY:
        await update.message.reply_text("Agnes API Key is missing!")
        return

    try:
        photo = update.message.photo[-1]
        telegram_file = await context.bot.get_file(photo.file_id)
        image_bytes = await telegram_file.download_as_bytearray()

        image_base64 = base64.b64encode(bytes(image_bytes)).decode("utf-8")
        context.user_data["video_first_frame"] = (
            "data:image/jpeg;base64," + image_base64
        )
        context.user_data["mode"] = "video_image_prompt"

        await update.message.reply_text(
            " Image received!\n\n"
            "Now send a prompt describing how you want the image to move."
        )

    except Exception as e:
        context.user_data["mode"] = "video_image_photo"
        await update.message.reply_text(
            f"Could not process image:\n{str(e)[:500]}"
        )


# Generate video with Agnes API
async def generate_video(update: Update, prompt: str, mode: str, first_frame=None):
    if not AGNES_API_KEY:
        await update.message.reply_text("Agnes API Key is missing!")
        return

    status_msg = await update.message.reply_text(
        " Your video is being generated...\n"
        "This may take several minutes. Please wait."
    )

    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": VIDEO_MODEL,
        "prompt": prompt,
        "mode": mode,
        "seconds": "5",
        "size": "720P",
        "aspect_ratio": "16:9",
        "n": 1,
    }

    if first_frame:
        payload["first_frame"] = first_frame

    try:
        async with httpx.AsyncClient(timeout=60.0) as http:
            
            # Create video task with automatic retry
            result = None

            for retry in range(5):
                response = await http.post(
                    f"{VIDEO_API}/v1/videos",
                    headers=headers,
                    json=payload,
                )

                if response.status_code == 503 and retry < 4:
                    wait_time = 15 * (2 ** retry)

                    try:
                        await status_msg.edit_text(
                            f"⚠️ Agnes Video Server is busy.\n"
                            f"Retrying in {wait_time} seconds...\n"
                            f"Attempt {retry + 2}/5"
                        )
                    except Exception:
                        pass

                    await asyncio.sleep(wait_time)
                    continue

                response.raise_for_status()
                result = response.json()
                break

            if result is None:
                raise Exception(
                    f"Video server is still unavailable: "
                    f"{response.text[:500]}"
                )


            video_id = result.get("video_id") or result.get("id")

            if not video_id:
                raise Exception(f"No video_id returned: {result}")

            await status_msg.edit_text(
                " Video task started!\n"
                "Waiting for video generation..."
            )

            # Poll video result
            video_url = None

            for attempt in range(90):
                await asyncio.sleep(10)

                poll_response = await http.get(
                    f"{VIDEO_API}/agnesapi",
                    headers=headers,
                    params={
                        "video_id": video_id,
                        "model_name": VIDEO_MODEL,
                    },
                )
                poll_response.raise_for_status()
                data = poll_response.json()

                status = str(data.get("status", "")).lower()

                if status == "completed":
                    video_url = data.get("url")
                    if not video_url:
                        raise Exception(
                            f"Video completed but URL is missing: {data}"
                        )
                    break

                if status in ("failed", "error", "cancelled"):
                    raise Exception(
                        data.get("error") or "Video generation failed."
                    )

                if attempt in (5, 15, 30, 45, 60, 75):
                    try:
                        await status_msg.edit_text(
                            f"⏳ Video is still generating...\n"
                            f"Please wait. ({(attempt + 1) * 10} seconds)"
                        )
                    except Exception:
                        pass


            if not video_url:
                raise Exception(
                    "Video generation timed out. Please try again later."
                )

            await status_msg.edit_text(
                " Video ready! Downloading..."
            )

            # Download generated video
            download_response = await http.get(
                video_url,
                timeout=180.0,
            )
            download_response.raise_for_status()
            video_bytes = download_response.content

            # Telegram Bot API video upload limit can apply
            if len(video_bytes) > 49 * 1024 * 1024:
                await status_msg.edit_text(
                    "Video generated, but it is too large to send through Telegram."
                )
                return

            await update.message.reply_video(
                video=video_bytes,
                filename="agnes-video.mp4",
                caption=" Your AI Video is ready!",
                read_timeout=180,
                write_timeout=180,
                connect_timeout=60,
                pool_timeout=60,
            )

            await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(
            f" Video generation failed:\n{str(e)[:800]}"
        )


# Text prompt handler
async def prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")

    if not mode:
        await update.message.reply_text(
            "Please choose a service using /start."
        )
        return

    prompt = update.message.text.strip()

    if not prompt:
        await update.message.reply_text("Please enter a prompt.")
        return

    if mode == "image":
        context.user_data["mode"] = None

        if not AGNES_API_KEY:
            await update.message.reply_text("Agnes API Key is missing!")
            return

        msg = await update.message.reply_text(
            " Generating your image... Please wait!"
        )

        try:
            result = await asyncio.to_thread(
                client.images.generate,
                model="agnes-image-2.5-flash",
                prompt=prompt,
                size="1K",
                extra_body={
                    "ratio": "1:1",
                    "response_format": "url"
                }
            )

            image_url = result.data[0].url

            await update.message.reply_photo(
                photo=image_url,
                caption=" Your AI Image is ready!"
            )

            await msg.delete()

        except Exception as e:
            await msg.edit_text(
                f" Image generation failed:\n{str(e)[:800]}"
            )

    elif mode == "video_text":
        context.user_data["mode"] = None
        await generate_video(
            update,
            prompt,
            mode="text",
        )

    elif mode == "video_image_prompt":
        first_frame = context.user_data.get("video_first_frame")
        context.user_data["mode"] = None
        context.user_data.pop("video_first_frame", None)

        if not first_frame:
            await update.message.reply_text(
                "Image is missing. Please start again with /start."
            )
            return

        await generate_video(
            update,
            prompt,
            mode="keyframe",
            first_frame=first_frame,
        )


# Cancel command
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(" Request cancelled.")


# Main function
def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is missing!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Photo handler must be registered before text handler
    app.add_handler(
        MessageHandler(filters.PHOTO, photo_handler)
    )

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, prompt_handler)
    )

    threading.Thread(
        target=run_web_server,
        daemon=True
    ).start()

    print("AI Image & Video Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()
