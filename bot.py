# --- imports ---
import logging
import asyncio
import os
import json
import threading
from collections import deque
from flask import Flask
import aiohttp
from telegram import Update, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
)

# --- logging ---
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

# --- env ---
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = int(os.environ.get('CHAT_ID')) if os.environ.get('CHAT_ID') else None

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN missing")

SETTINGS_FILE = "bot_settings.json"
SEEN_FILE = "seen_ads.json"

# --- defaults ---
DEFAULT_SETTINGS = {
    "min_price": 0,
    "max_price": 0,
    "min_area": 0,
    "max_area": 0,
    "has_parking": False,
    "has_elevator": False,
    "has_warehouse": False,
    "query": ""
}

# --- helpers ---
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except:
            pass
    return default


def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


user_settings = load_json(SETTINGS_FILE, DEFAULT_SETTINGS.copy())
seen_ads = deque(load_json(SEEN_FILE, []), maxlen=1000)

# --- flask keep alive ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is Alive", 200


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- divar api ---
DIVAR_SEARCH_URL = "https://api.divar.ir/v8/web-search/karaj/buy-apartment"
DIVAR_POST_URL = "https://api.divar.ir/v8/posts/{}"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json"
}


async def get_ad_photos(session, token):
    async with session.get(DIVAR_POST_URL.format(token)) as resp:
        if resp.status != 200:
            return []
        data = await resp.json()
        images = []
        for w in data.get('widgets', {}).get('list', []):
            if w.get('widget_type') == 'IMAGE_CAROUSEL':
                for i in w.get('data', {}).get('items', []):
                    if 'image_url' in i:
                        images.append(i['image_url'])
        return images


async def fetch_divar_ads(session):
    schema = {
        "category": {"value": "buy-apartment"},
        "cities": ["karaj"]
    }

    if user_settings['min_price'] or user_settings['max_price']:
        schema['price'] = {
            k: v for k, v in {
                'min': user_settings['min_price'],
                'max': user_settings['max_price']
            }.items() if v
        }

    if user_settings['min_area'] or user_settings['max_area']:
        schema['size'] = {
            k: v for k, v in {
                'min': user_settings['min_area'],
                'max': user_settings['max_area']
            }.items() if v
        }

    for key in ['has_parking', 'has_elevator', 'has_warehouse']:
        if user_settings[key]:
            schema[key.replace('_', '-')] = {"value": True}

    payload = {
        "json_schema": schema,
        "last-post-date": 0,
        "query": user_settings['query']
    }

    async with session.post(DIVAR_SEARCH_URL, json=payload, headers=HEADERS) as resp:
        if resp.status != 200:
            return []
        data = await resp.json()
        return data.get('web_widgets', {}).get('post_list', [])


async def process_ads(context: ContextTypes.DEFAULT_TYPE, chat_id):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        ads = await fetch_divar_ads(session)
        for ad in reversed(ads[-5:]):
            data = ad.get('data', {})
            token = data.get('token')
            if not token or token in seen_ads:
                continue

            caption = (
                f"🏠 <b>{data.get('title')}</b>\n"
                f"📍 {data.get('district', '')}\n"
                f"💰 {data.get('middle_description_text', '')}\n\n"
                f"🔗 <a href='https://divar.ir/v/a/{token}'>مشاهده</a>"
            )

            images = await get_ad_photos(session, token)
            if images:
                media = [InputMediaPhoto(images[0], caption=caption, parse_mode='HTML')]
                for img in images[1:4]:
                    media.append(InputMediaPhoto(img))
                await context.bot.send_media_group(chat_id, media)
            else:
                await context.bot.send_message(chat_id, caption, parse_mode='HTML')

            seen_ads.append(token)

        save_json(SEEN_FILE, list(seen_ads))

# --- telegram commands (INLINE UI) ---
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_settings_menu(update, context)


async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 قیمت", callback_data="set_price")],
        [InlineKeyboardButton("📐 متراژ", callback_data="set_area")],
        [InlineKeyboardButton("🚗 پارکینگ", callback_data="toggle_parking")],
        [InlineKeyboardButton("🛗 آسانسور", callback_data="toggle_elevator")],
        [InlineKeyboardButton("📦 انباری", callback_data="toggle_warehouse")],
        [InlineKeyboardButton("🔎 جستجو", callback_data="set_query")],
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="manual_update")],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    text = (
        "⚙️ تنظیمات فیلتر دیوار\n\n"
        f"💰 قیمت: {user_settings['min_price']} - {user_settings['max_price']}\n"
        f"📐 متراژ: {user_settings['min_area']} - {user_settings['max_area']}\n"
        f"🚗 پارکینگ: {'✅' if user_settings['has_parking'] else '❌'}\n"
        f"🛗 آسانسور: {'✅' if user_settings['has_elevator'] else '❌'}\n"
        f"📦 انباری: {'✅' if user_settings['has_warehouse'] else '❌'}\n"
        f"🔎 جستجو: {user_settings['query'] or '-'}"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    context.user_data.clear()

    if data == "set_price":
        context.user_data['await'] = 'price'
        await query.message.reply_text("حداقل و حداکثر قیمت را وارد کن:\nمثال: 3000000000 7000000000")
    elif data == "set_area":
        context.user_data['await'] = 'area'
        await query.message.reply_text("حداقل و حداکثر متراژ را وارد کن:\nمثال: 80 140")
    elif data.startswith("toggle_"):
        key = data.replace("toggle_", "has_")
        user_settings[key] = not user_settings[key]
        save_json(SETTINGS_FILE, user_settings)
        await show_settings_menu(update, context)
    elif data == "set_query":
        context.user_data['await'] = 'query'
        await query.message.reply_text("متن جستجو را وارد کن:")
    elif data == "manual_update":
        await query.message.reply_text("در حال بررسی...")
        await process_ads(context, query.message.chat_id)
        await query.message.reply_text("تمام شد")


async def text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'await' not in context.user_data:
        return

    mode = context.user_data.pop('await')
    text = update.message.text.strip()

    try:
        if mode == 'price':
            a, b = map(int, text.split())
            user_settings['min_price'], user_settings['max_price'] = a, b
        elif mode == 'area':
            a, b = map(int, text.split())
            user_settings['min_area'], user_settings['max_area'] = a, b
        elif mode == 'query':
            user_settings['query'] = text
        save_json(SETTINGS_FILE, user_settings)
        await show_settings_menu(update, context)
    except:
        await update.message.reply_text("❌ ورودی نامعتبر است")

# --- main ---
if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()

    app_tg = ApplicationBuilder().token(TOKEN).build()

    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CommandHandler("help", help_cmd))
    app_tg.add_handler(CommandHandler("set_price", set_price))
    app_tg.add_handler(CommandHandler("set_area", set_area))
    app_tg.add_handler(CommandHandler("parking", lambda u, c: toggle(u, c, 'has_parking')))
    app_tg.add_handler(CommandHandler("elevator", lambda u, c: toggle(u, c, 'has_elevator')))
    app_tg.add_handler(CommandHandler("warehouse", lambda u, c: toggle(u, c, 'has_warehouse')))
    app_tg.add_handler(CommandHandler("update", manual_update))

    if CHAT_ID:
        app_tg.job_queue.run_repeating(scheduled_job, interval=3600, first=10)

    app_tg.run_polling()
