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

# --- telegram commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ربات فعال است ✅\n/help")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/set_price min max\n"
        "/set_area min max\n"
        "/parking on|off\n"
        "/elevator on|off\n"
        "/warehouse on|off\n"
        "/query متن\n"
        "/update"
    )


async def set_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_settings['min_price'] = int(context.args[0])
    user_settings['max_price'] = int(context.args[1])
    save_json(SETTINGS_FILE, user_settings)
    await update.message.reply_text("✅ قیمت تنظیم شد")


async def set_area(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_settings['min_area'] = int(context.args[0])
    user_settings['max_area'] = int(context.args[1])
    save_json(SETTINGS_FILE, user_settings)
    await update.message.reply_text("✅ متراژ تنظیم شد")


async def toggle(update: Update, context: ContextTypes.DEFAULT_TYPE, key):
    user_settings[key] = context.args[0].lower() == 'on'
    save_json(SETTINGS_FILE, user_settings)
    await update.message.reply_text(f"✅ {key} تنظیم شد")


async def manual_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("در حال بررسی...")
    await process_ads(context, update.effective_chat.id)
    await update.message.reply_text("تمام شد")


async def scheduled_job(context: ContextTypes.DEFAULT_TYPE):
    await process_ads(context, CHAT_ID)

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
