import logging
import asyncio
import os
import json
import requests
import threading
import random
from flask import Flask
from telegram import Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# --- تنظیمات لاگ ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

# --- متغیرها ---
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

if not TOKEN or not CHAT_ID:
    logging.critical("🚨 ERROR: TOKEN or CHAT_ID is missing!")

SETTINGS_FILE = "bot_settings.json"
SEEN_FILE = "seen_ads.json"

DEFAULT_SETTINGS = {
    "min_price": 0, "max_price": 0,
    "min_area": 0, "max_area": 0,
    "has_parking": False, "has_elevator": False, "has_warehouse": False,
    "query": ""
}

# --- مدیریت فایل‌ها ---
def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f: return json.load(f)
        except: pass
    return default

def save_json(filename, data):
    try:
        if isinstance(data, set): data = list(data)[-1000:]
        with open(filename, 'w') as f: json.dump(data, f)
    except: pass

user_settings = load_json(SETTINGS_FILE, DEFAULT_SETTINGS.copy())
seen_ads = set(load_json(SEEN_FILE, []))

# --- وب‌سرور ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is Alive!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- توابع دیوار ---
async def get_ad_photos(token):
    # دریافت عکس‌ها با هدرهای واقعی
    url = f"https://api.divar.ir/v8/posts/{token}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://divar.ir/',
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            widgets = data.get('widgets', {}).get('list', [])
            images = []
            for widget in widgets:
                if widget.get('widget_type') == 'IMAGE_CAROUSEL':
                    items = widget.get('data', {}).get('items', [])
                    for item in items:
                        if 'image_url' in item: images.append(item['image_url'])
            return images
    except: pass
    return []

async def fetch_divar_ads():
    url = "https://api.divar.ir/v8/web-search/karaj/buy-apartment"
    
    # تنظیمات دقیق Payload
    json_schema = {
        "category": {"value": "buy-apartment"},
        "cities": ["karaj"],
    }

    # فیلترها
    price_d = {}
    if user_settings.get("min_price"): price_d["min"] = user_settings["min_price"]
    if user_settings.get("max_price"): price_d["max"] = user_settings["max_price"]
    if price_d: json_schema["price"] = price_d

    area_d = {}
    if user_settings.get("min_area"): area_d["min"] = user_settings["min_area"]
    if user_settings.get("max_area"): area_d["max"] = user_settings["max_area"]
    if area_d: json_schema["size"] = area_d

    if user_settings.get("has_parking"): json_schema["has-parking"] = {"value": True}
    if user_settings.get("has_elevator"): json_schema["has-elevator"] = {"value": True}
    if user_settings.get("has_warehouse"): json_schema["has-warehouse"] = {"value": True}

    payload = {
        "json_schema": json_schema,
        "last-post-date": 0 
    }
    
    if user_settings.get("query"):
        payload["query"] = user_settings["query"]

    # هدرهای کامل برای شبیه‌سازی مرورگر
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7',
        'Origin': 'https://divar.ir',
        'Referer': 'https://divar.ir/s/karaj/buy-apartment',
        'Content-Type': 'application/json',
        'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"'
    }

    try:
        logging.info(f"📤 Payload sending: {json.dumps(payload, ensure_ascii=False)}")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # مسیر جدید در پاسخ‌های دیوار
            ads = data.get('web_widgets', {}).get('post_list', [])
            logging.info(f"✅ Divar Response: Found {len(ads)} ads.")
            return ads
        else:
            logging.error(f"❌ Divar API Status: {response.status_code} - {response.text[:100]}")
    except Exception as e:
        logging.error(f"❌ Connection Error: {e}")
    return []

async def process_ads(context: ContextTypes.DEFAULT_TYPE, target_chat_id):
    if not target_chat_id: return

    ads = await fetch_divar_ads()
    if not ads:
        logging.info("💤 List is empty.")
        return

    new_count = 0
    # فقط 5 تای آخر
    for ad in reversed(ads[:5]):
        data = ad.get('data', {})
        token = data.get('token')
        
        if not token or token in seen_ads:
            continue
            
        title = data.get('title', 'بدون عنوان')
        price = data.get('middle_description_text', '')
        district = data.get('district', '')
        # برخی آگهی‌ها عکس ندارند و image_url خالی است
        image_url = data.get('image_url') 
        link = f"https://divar.ir/v/a/{token}"
        
        caption = f"🏠 <b>{title}</b>\n📍 {district}\n💰 {price}\n\n🔗 <a href='{link}'>مشاهده</a>"

        try:
            # دریافت آلبوم (فقط اگر عکس اصلی وجود داشت تلاش کن)
            images = []
            if image_url:
                await asyncio.sleep(random.uniform(1.5, 3.0)) # تاخیر تصادفی
                images = await get_ad_photos(token)
            
            if images and len(images) > 0:
                media = [InputMediaPhoto(images[0], caption=caption, parse_mode='HTML')]
                for img in images[1:4]:
                    media.append(InputMediaPhoto(img))
                await context.bot.send_media_group(target_chat_id, media=media)
            elif image_url:
                 await context.bot.send_photo(target_chat_id, photo=image_url, caption=caption, parse_mode='HTML')
            else:
                await context.bot.send_message(target_chat_id, text=caption, parse_mode='HTML')
            
            seen_ads.add(token)
            new_count += 1
            
        except Exception as e:
            logging.error(f"⚠️ Send Error: {e}")

    if new_count > 0:
        save_json(SEEN_FILE, seen_ads)
        logging.info(f"📤 Sent {new_count} ads.")

# --- هندلرها ---
async def start(update, context): await update.message.reply_text("🤖 ربات آماده است. /update را بزنید.")
async def manual_update(update, context): 
    await update.message.reply_text("🔄 جستجو...")
    await process_ads(context, update.effective_chat.id)
    await update.message.reply_text("✅ پایان.")

# تنظیم مقادیر (ساده شده برای جلوگیری از خطا)
async def set_command(update, context):
    try:
        cmd = update.message.text.split()[0][1:] # min_price
        val = int(context.args[0])
        # مپ کردن دستورات به کلیدهای تنظیمات
        key_map = {
            "min": "min_price", "max": "max_price",
            "minarea": "min_area", "maxarea": "max_area"
        }
        if cmd in key_map:
            user_settings[key_map[cmd]] = val
            save_json(SETTINGS_FILE, user_settings)
            await update.message.reply_text(f"✅ {key_map[cmd]} = {val}")
    except: await update.message.reply_text("❌ خطا در مقداردهی")

async def status(update, context):
    await update.message.reply_text(f"📊 {json.dumps(user_settings, indent=2, ensure_ascii=False)}")

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    
    if not TOKEN: exit(1)

    app_bot = ApplicationBuilder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("update", manual_update))
    app_bot.add_handler(CommandHandler("status", status))
    # هندلرهای تنظیم قیمت و متراژ
    app_bot.add_handler(CommandHandler(["min", "max", "minarea", "maxarea"], set_command))

    if CHAT_ID:
        # چک کردن هر 30 دقیقه (تایم کمتر ممکن است باعث بلاک شدن شود)
        app_bot.job_queue.run_repeating(lambda c: process_ads(c, CHAT_ID), interval=1800, first=10)

    app_bot.run_polling()
