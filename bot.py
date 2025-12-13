import logging
import os
import json
import threading
import time
from collections import deque

# کتابخانه جدید برای دور زدن محدودیت‌ها
import tls_client
from flask import Flask

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# --- تنظیمات لاگ ---
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)

# --- توکن‌ها ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
try:
    CHAT_ID = int(CHAT_ID) if CHAT_ID else None
except:
    pass

SETTINGS_FILE = "bot_settings.json"
SEEN_FILE = "seen_ads.json"

DEFAULT_SETTINGS = {
    "min_price": 0, "max_price": 0,
    "min_area": 0, "max_area": 0,
    "has_parking": False, "has_elevator": False, "has_warehouse": False,
    "query": "",
}

# --- مدیریت فایل ---
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding='utf-8') as f: return json.load(f)
        except: pass
    return default

def save_json(path, data):
    with open(path, "w", encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

user_settings = load_json(SETTINGS_FILE, DEFAULT_SETTINGS.copy())
seen_ads = deque(load_json(SEEN_FILE, []), maxlen=1000)

# --- وب‌سرور ---
app = Flask(__name__)
@app.route("/")
def home(): return "Bot is running with TLS spoofing!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- کلاینت دیوار (ضد تشخیص) ---
def get_divar_client():
    """ساخت یک کلاینت که خود را جای مرورگر کروم جا می‌زند"""
    session = tls_client.Session(
        client_identifier="chrome_120",
        random_tls_extension_order=True
    )
    return session

def fetch_ads_from_divar():
    """دریافت آگهی‌ها با کلاینت مخصوص"""
    url = "https://api.divar.ir/v8/web-search/karaj/buy-apartment"
    
    schema = {
        "category": {"value": "buy-apartment"},
        "cities": ["karaj"],
    }

    # اعمال فیلترها
    price_filter = {}
    if user_settings["min_price"] > 0: price_filter["min"] = user_settings["min_price"]
    if user_settings["max_price"] > 0: price_filter["max"] = user_settings["max_price"]
    if price_filter: schema["price"] = price_filter

    size_filter = {}
    if user_settings["min_area"] > 0: size_filter["min"] = user_settings["min_area"]
    if user_settings["max_area"] > 0: size_filter["max"] = user_settings["max_area"]
    if size_filter: schema["size"] = size_filter

    if user_settings["has_parking"]: schema["has-parking"] = {"value": True}
    if user_settings["has_elevator"]: schema["has-elevator"] = {"value": True}
    if user_settings["has_warehouse"]: schema["has-warehouse"] = {"value": True}

    payload = {
        "json_schema": schema,
        "last-post-date": 0,
    }
    if user_settings["query"]: payload["query"] = user_settings["query"]

    # هدرهای کاملاً واقعی
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://divar.ir",
        "Referer": "https://divar.ir/s/karaj/buy-apartment",
    }

    try:
        session = get_divar_client()
        # استفاده از TLS Client برای درخواست POST
        response = session.post(url, json=payload, headers=headers)
        
        logging.info(f"📡 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            widgets = data.get("web_widgets", {}).get("post_list", [])
            logging.info(f"✅ Found {len(widgets)} ads via TLS Client.")
            return widgets
        else:
            logging.error(f"❌ Error Body: {response.text[:200]}")
            
    except Exception as e:
        logging.error(f"❌ Fetch Error: {e}")
    
    return []

def get_photos(token):
    url = f"https://api.divar.ir/v8/posts/{token}"
    try:
        session = get_divar_client()
        resp = session.get(url)
        if resp.status_code == 200:
            data = resp.json()
            images = []
            for w in data.get("widgets", {}).get("list", []):
                if w.get("widget_type") == "IMAGE_CAROUSEL":
                    for item in w.get("data", {}).get("items", []):
                        if "image_url" in item: images.append(item["image_url"])
            return images
    except: pass
    return []

async def check_updates(context: ContextTypes.DEFAULT_TYPE, chat_id):
    # چون tls_client ناهمگام نیست، آن را مستقیم صدا می‌زنیم (در ترید جداگانه هندل می‌شود)
    ads = fetch_ads_from_divar()
    
    if not ads:
        return 0

    new_count = 0
    for ad in reversed(ads[:10]):
        data = ad.get("data", {})
        token = data.get("token")
        
        if not token or token in seen_ads:
            continue
            
        title = data.get("title", "آگهی")
        price = data.get("middle_description_text", "")
        district = data.get("district", "")
        
        caption = (
            f"🏠 <b>{title}</b>\n"
            f"📍 {district}\n"
            f"💰 {price}\n\n"
            f"🔗 <a href='https://divar.ir/v/a/{token}'>مشاهده</a>"
        )
        
        try:
            images = get_photos(token)
            if images:
                media = [InputMediaPhoto(images[0], caption=caption, parse_mode="HTML")]
                for img in images[1:4]: media.append(InputMediaPhoto(img))
                await context.bot.send_media_group(chat_id, media=media)
            else:
                await context.bot.send_message(chat_id, caption, parse_mode="HTML")
            
            seen_ads.append(token)
            new_count += 1
            time.sleep(1) # تاخیر کم
            
        except Exception as e:
            logging.error(f"Send Error: {e}")

    if new_count > 0:
        save_json(SEEN_FILE, list(seen_ads))
    return new_count

# --- UI ---
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = user_settings
    status = (
        "📊 <b>وضعیت ربات</b>\n"
        f"💰 قیمت: {s['min_price']:,} - {s['max_price']:,}\n"
        f"📏 متراژ: {s['min_area']} - {s['max_area']}\n"
        f"🔎 جستجو: {s['query']}\n"
        f"🚗 P: {'✅' if s['has_parking'] else '❌'} | 🛗 E: {'✅' if s['has_elevator'] else '❌'}"
    )
    kb = [
        [InlineKeyboardButton("💰 قیمت", callback_data="set_price"), InlineKeyboardButton("📏 متراژ", callback_data="set_area")],
        [InlineKeyboardButton("🔎 کلمه کلیدی", callback_data="set_query")],
        [InlineKeyboardButton("تغییر امکانات (P/E/W)", callback_data="toggle_opts")],
        [InlineKeyboardButton("🔄 اسکن دستی", callback_data="update")]
    ]
    markup = InlineKeyboardMarkup(kb)
    if update.callback_query: await update.callback_query.edit_message_text(status, reply_markup=markup, parse_mode="HTML")
    else: await update.message.reply_text(status, reply_markup=markup, parse_mode="HTML")

async def btn_handler(update, context):
    q = update.callback_query
    await q.answer()
    data = q.data
    
    if data == "update":
        await q.message.reply_text("🔎 در حال اسکن...")
        c = await check_updates(context, q.message.chat_id)
        await q.message.reply_text(f"✅ {c} آگهی جدید.")
        return

    if data == "toggle_opts":
        # ساده‌سازی: چرخش بین حالات (فعلاً فقط پارکینگ را تاگل می‌کنیم برای نمونه)
        user_settings["has_parking"] = not user_settings["has_parking"]
        save_json(SETTINGS_FILE, user_settings)
        await show_menu(update, context)
        return

    context.user_data['mode'] = data
    await q.message.reply_text("✍️ لطفاً مقادیر را با فاصله بفرستید (مثال: `0 0` برای حذف):")

async def txt_handler(update, context):
    mode = context.user_data.get('mode')
    if not mode: return
    txt = update.message.text.split()
    try:
        if mode == "set_price":
            user_settings["min_price"], user_settings["max_price"] = int(txt[0]), int(txt[1])
        elif mode == "set_area":
            user_settings["min_area"], user_settings["max_area"] = int(txt[0]), int(txt[1])
        elif mode == "set_query":
            user_settings["query"] = update.message.text if update.message.text != "0" else ""
            
        save_json(SETTINGS_FILE, user_settings)
        context.user_data.clear()
        await show_menu(update, context)
    except: await update.message.reply_text("❌ خطا در فرمت.")

# --- اجرا ---
async def job_scan(context):
    if CHAT_ID: await check_updates(context, CHAT_ID)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    if not TOKEN: exit(1)
    
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", show_menu))
    app.add_handler(CallbackQueryHandler(btn_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, txt_handler))
    
    if CHAT_ID:
        app.job_queue.run_repeating(job_scan, interval=1800, first=10)
        
    app.run_polling()
