import logging
import asyncio
import os
import json
import requests
import threading
from flask import Flask
from telegram import Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# --- تنظیمات لاگ (تمیز کردن لاگ‌های اضافی) ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
# بستن لاگ‌های شلوغ کتابخانه‌های دیگر
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

# --- دریافت متغیرها ---
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

# بررسی حیاتی تنظیمات
if not TOKEN:
    logging.error("❌ ERROR: TELEGRAM_BOT_TOKEN is missing in Environment Variables!")
if not CHAT_ID:
    logging.error("❌ ERROR: CHAT_ID is missing in Environment Variables!")

SETTINGS_FILE = "bot_settings.json"
SEEN_FILE = "seen_ads.json"

# تنظیمات پیش‌فرض
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
        # تبدیل set به list برای ذخیره جیسون
        if isinstance(data, set):
            data = list(data)[-1000:]
        with open(filename, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logging.error(f"Save Error: {e}")

user_settings = load_json(SETTINGS_FILE, DEFAULT_SETTINGS.copy())
seen_ads = set(load_json(SEEN_FILE, []))

# --- وب‌سرور Flask ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is Alive & Running!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- توابع دیوار ---
async def get_ad_photos(token):
    url = f"https://api.divar.ir/v8/posts/{token}"
    try:
        response = requests.get(url, timeout=5)
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
    """دریافت آگهی‌ها از دیوار"""
    url = "https://api.divar.ir/v8/web-search/karaj/buy-apartment"
    
    json_schema = {
        "category": {"value": "buy-apartment"},
        "cities": ["karaj"],
    }

    # اعمال فیلترها
    price_d = {}
    if user_settings["min_price"]: price_d["min"] = user_settings["min_price"]
    if user_settings["max_price"]: price_d["max"] = user_settings["max_price"]
    if price_d: json_schema["price"] = price_d

    area_d = {}
    if user_settings["min_area"]: area_d["min"] = user_settings["min_area"]
    if user_settings["max_area"]: area_d["max"] = user_settings["max_area"]
    if area_d: json_schema["size"] = area_d

    if user_settings["has_parking"]: json_schema["has-parking"] = {"value": True}
    if user_settings["has_elevator"]: json_schema["has-elevator"] = {"value": True}
    if user_settings["has_warehouse"]: json_schema["has-warehouse"] = {"value": True}

    payload = {"json_schema": json_schema, "last-post-date": 0}
    if user_settings["query"]: payload["query"] = user_settings["query"]

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'application/json'
    }

    try:
        logging.info("🌍 Sending request to Divar...")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            ads = response.json().get('web_widgets', {}).get('post_list', [])
            logging.info(f"✅ Divar Response: Found {len(ads)} ads.")
            return ads
        else:
            logging.error(f"❌ Divar API Error: Status {response.status_code}")
    except Exception as e:
        logging.error(f"❌ Connection Error: {e}")
    return []

async def process_ads(context: ContextTypes.DEFAULT_TYPE, target_chat_id):
    """پردازش و ارسال آگهی‌ها"""
    if not target_chat_id:
        logging.error("❌ Cannot send ads: CHAT_ID is missing!")
        return

    ads = await fetch_divar_ads()
    if not ads:
        return

    new_count = 0
    # فقط 5 آگهی آخر برای جلوگیری از ترافیک بالا در شروع
    for ad in reversed(ads[:5]):
        data = ad.get('data', {})
        token = data.get('token')
        
        if not token or token in seen_ads:
            continue
            
        title = data.get('title', 'بدون عنوان')
        price = data.get('middle_description_text', '')
        district = data.get('district', '')
        link = f"https://divar.ir/v/a/{token}"
        
        caption = f"🏠 <b>{title}</b>\n📍 {district}\n💰 {price}\n\n🔗 <a href='{link}'>مشاهده</a>"

        try:
            # سعی در دریافت عکس
            await asyncio.sleep(1) # تاخیر
            images = await get_ad_photos(token)
            
            if images and len(images) > 0:
                media = [InputMediaPhoto(images[0], caption=caption, parse_mode='HTML')]
                # افزودن تا 3 عکس دیگر به آلبوم
                for img in images[1:4]:
                    media.append(InputMediaPhoto(img))
                await context.bot.send_media_group(target_chat_id, media=media)
            else:
                await context.bot.send_message(target_chat_id, text=caption, parse_mode='HTML')
            
            seen_ads.add(token)
            new_count += 1
            
        except Exception as e:
            logging.error(f"⚠️ Telegram Send Error: {e}")

    if new_count > 0:
        save_json(SEEN_FILE, seen_ads)
        logging.info(f"📤 Sent {new_count} new ads.")
    else:
        logging.info("💤 No new ads found.")

# --- دستورات تلگرام ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 ربات متصل است! دستور /update را بزنید.")

async def manual_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 در حال بررسی...")
    await process_ads(context, update.effective_chat.id)
    await update.message.reply_text("✅ بررسی تمام شد.")

# --- جاب زمان‌بندی شده ---
async def scheduled_job(context: ContextTypes.DEFAULT_TYPE):
    """این تابع توسط تایمر اجرا می‌شود"""
    logging.info("⏰ Scheduled job started...")
    await process_ads(context, CHAT_ID)

# --- بدنه اصلی ---
if __name__ == '__main__':
    # اجرای وب سرور
    threading.Thread(target=run_flask, daemon=True).start()

    if not TOKEN:
        logging.critical("🚨 BOT TOKEN IS MISSING. BOT WILL STOP.")
        exit(1)

    application = ApplicationBuilder().token(TOKEN).build()
    
    # هندلرها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("update", manual_update))
    
    # تنظیم جاب
    if CHAT_ID:
        job_queue = application.job_queue
        # اولین اجرا بعد از 10 ثانیه، سپس هر 1 ساعت
        job_queue.run_repeating(scheduled_job, interval=3600, first=10)
        logging.info(f"✅ Job scheduled for Chat ID: {CHAT_ID}")
    else:
        logging.warning("⚠️ No CHAT_ID found. Auto-updates disabled!")

    logging.info("🚀 Bot is polling...")
    application.run_polling()
