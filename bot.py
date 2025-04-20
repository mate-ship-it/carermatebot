import os
import tempfile
import aiohttp
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from openai import OpenAI

# ───────────────────────────────────────────────────────────────────────────────
# Configuration
# ───────────────────────────────────────────────────────────────────────────────
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
raw_ids = os.getenv("AUTHORIZED_CHAT_ID", "")
AUTHORIZED_CHAT_IDS = [int(x) for x in raw_ids.split(",") if x.strip().isdigit()]

client = OpenAI(api_key=OPENAI_API_KEY)


# ───────────────────────────────────────────────────────────────────────────────
# Authorization Helper
# ───────────────────────────────────────────────────────────────────────────────
def is_authorized(chat_id: int) -> bool:
    """Check if the chat ID is in the list of authorized users."""
    return chat_id in AUTHORIZED_CHAT_IDS


# ───────────────────────────────────────────────────────────────────────────────
# Command Handlers
# ───────────────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start: greet the user and show main menu."""
    chat_id = update.effective_chat.id
    if not is_authorized(chat_id):
        await update.message.reply_text("❌ You are not authorised to use this bot.")
        return

    keyboard = [["Help", "Write", "Record"]]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Hi! Please choose an option below:", reply_markup=markup
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process incoming text messages."""
    chat_id = update.effective_chat.id
    if not is_authorized(chat_id):
        await update.message.reply_text("❌ You are not authorised to use this bot.")
        return

    text = update.message.text.strip().lower()

    if text == "help":
        await update.message.reply_text("🆘 What do you need help with?")
    elif text == "write":
        await update.message.reply_text("✍️ Please type what you'd like me to help you write.")
    elif text == "record":
        await update.message.reply_text("🎙️ Please send a voice message.")
    else:
        await process_with_gpt(update, text)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Download voice message, transcribe it, and process with GPT."""
    chat_id = update.effective_chat.id
    if not is_authorized(chat_id):
        await update.message.reply_text("❌ You are not authorised to use this bot.")
        return

    # Download voice to temp file
    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
        async with aiohttp.ClientSession() as session:
            async with session.get(file.file_path) as resp:
                tmp.write(await resp.read())
        audio_path = tmp.name

    # Transcribe & process
    try:
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        os.remove(audio_path)

        user_text = transcript.text
        await process_with_gpt(update, user_text, system_prompt="You are a helpful assistant.")
    except Exception:
        os.remove(audio_path)
        await update.message.reply_text("⚠️ Error while transcribing or processing the voice message.")


# ───────────────────────────────────────────────────────────────────────────────
# GPT Processing
# ───────────────────────────────────────────────────────────────────────────────
async def process_with_gpt(
    update: Update,
    user_content: str,
    system_prompt: str = (
        "You are a professional rewriting assistant. "
        "When given bullet points, you MUST:\n"
        "- Transform them into a coherent narrative written in the first‑person voice.\n"
        "- Use English only—no other languages.\n"
        "- Write at least three sentences per paragraph and at least two paragraphs overall.\n"
        "- Maintain a clear, consistent tone appropriate for summarizing notes or reports.\n"
        "Do NOT add extra commentary or translate."
    )
) -> None:
    """Send content to GPT-4o and relay the response back to the user."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]
        )
        reply = response.choices[0].message.content
    except Exception:
        reply = "⚠️ Error while processing your message."

    await update.message.reply_text(reply)


# ───────────────────────────────────────────────────────────────────────────────
# Main Application Setup
# ───────────────────────────────────────────────────────────────────────────────
def main() -> None:
    """Start the Telegram bot."""
    if not all([BOT_TOKEN, OPENAI_API_KEY, AUTHORIZED_CHAT_IDS]):
        print("🚨 Missing configuration. Check your environment variables.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
