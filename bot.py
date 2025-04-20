import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
import aiohttp
import tempfile
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Read a comma-separated list of authorized chat IDs from the env var
raw_ids = os.getenv("AUTHORIZED_CHAT_ID", "")
AUTHORIZED_CHAT_IDS = [int(x) for x in raw_ids.split(",") if x.strip().isdigit()]

client = OpenAI(api_key=OPENAI_API_KEY)

def is_authorized(chat_id: int) -> bool:
    return chat_id in AUTHORIZED_CHAT_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("❌ You are not authorised to use this bot.")
        return

    keyboard = [["Help", "Write", "Record"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Hi! Please choose an option below:", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("❌ You are not authorised to use this bot.")
        return

    text = update.message.text.lower()

    if text == "help":
        await update.message.reply_text("🆘 What do you need help with?")
    elif text == "write":
        await update.message.reply_text("✍️ Please type what you'd like me to help you write.")
    elif text == "record":
        await update.message.reply_text("🎙️ Please send a voice message.")
    else:
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": text}
                ]
            )
            await update.message.reply_text(response.choices[0].message.content)
        except Exception:
            await update.message.reply_text("⚠️ Error while processing your message.")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("❌ You are not authorised to use this bot.")
        return

    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:
        async with aiohttp.ClientSession() as session:
            async with session.get(file.file_path) as resp:
                f.write(await resp.read())
        audio_path = f.name

    try:
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        os.remove(audio_path)

        user_text = transcript.text
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_text}
            ]
        )

        await update.message.reply_text(response.choices[0].message.content)
    except Exception:
        os.remove(audio_path)
        await update.message.reply_text("⚠️ Error while transcribing or processing the voice message.")

if __name__ == "__main__":
    if not BOT_TOKEN or not OPENAI_API_KEY or not AUTHORIZED_CHAT_IDS:
        print("🚨 Environment variables are missing or no authorized chat IDs set.")
        exit(1)

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("🤖 Bot is running...")
    app.run_polling()
