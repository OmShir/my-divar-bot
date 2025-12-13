import logging
import asyncio
import os
import json
import requests
import threading
import time
from flask import Flask
from telegram import Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from telegram.error import BadRequest

# --- تنظیمات ---
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
SETTINGS_FILE = "bot_settings.json"
SEEN_FILE = "seen_ads.json"

# تنظیمات پیش‌فرض
DEFAULT_SETTINGS = {
    "min_price": 0,
    "max_price": 0,
    "min_area": 0,       # حداقل متراژ
    "max_area": 0,       # حداکثر متراژ
    "has_parking": False,
    "has_elevator": False,
    "has_warehouse": False,
    "query": ""          # جستجوی متنی (مثلاً نام محله)
}

# --- مدیریت ذخیره و بازیابی اطلاعات ---
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f)

def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, 'r') as f:
                return set(json.load(f))
        except:
            pass
    return set()

def save_seen(seen_set):
    # فقط 1000 آگهی آخر را نگه می‌داریم تا فایل سنگین نشود
    limited_list = list(seen_set)[-1000:]
    with open(SEEN_FILE, 'w') as f:
        json.dump(limited_list, f)

# بارگذاری اولیه
user_settings = load_settings()
seen_ads = load_seen()

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- وب‌سرور Flask ---
app = Flask(__name__)
@app.route('/')
def home(): return "Advanced Divar Bot is Alive!", 200
def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# --- توابع دیوار ---

async def get_ad_photos(token):
    """دریافت تصاویر کامل یک آگهی"""
    url = f"https://api.divar.ir/v8/posts/{token}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            # استخراج عکس‌ها از بخش ویجت‌ها
            widgets = data.get('widgets', {}).get('list', [])
            images = []
            for widget in widgets:
                if widget.get('widget_type') == 'IMAGE_CAROUSEL':
                    items = widget.get('data', {}).get('items', [])
                    for item in items:
                        img_url = item.get('image_url')
                        if img_url:
                            images.append(img_url)
            return images
    except Exception as e:
        logging.error(f"Error fetching details for {token}: {e}")
    return []

async def fetch_divar_ads():
    url = "https://api.divar.ir/v8/web-search/karaj/buy-apartment"
    
    json_schema = {
        "category": {"value": "buy-apartment"},
        "cities": ["karaj"],
    }

    # فیلتر قیمت
    price_dict = {}
    if user_settings["min_price"] > 0: price_dict["min"] = user_settings["min_price"]
    if user_settings["max_price"] > 0: price_dict["max"] = user_settings["max_price"]
    if price_dict: json_schema["price"] = price_dict

    # فیلتر متراژ (جدید)
    area_dict = {}
    if user_settings["min_area"] > 0: area_dict["min"] = user_settings["min_area"]
    if user_settings["max_area"] > 0: area_dict["max"] = user_settings["max_area"]
    if area_dict: json_schema["size"] = area_dict

    # امکانات
    if user_settings["has_parking"]: json_schema["has-parking"] = {"value": True}
    if user_settings["has_elevator"]: json_schema["has-elevator"] = {"value": True}
    if user_settings["has_warehouse"]: json_schema["has-warehouse"] = {"value": True}

    # جستجوی متنی (محله)
    payload = {"json_schema": json_schema, "last-post-date": 0}
    if user_settings.get("query"):
        payload["query"] = user_settings["query"]

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Content-Type': 'application/json'}
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get('web_widgets', {}).get('post_list', [])
    except Exception as e:
        logging.error(f"Search API Error: {e}")
    return []

async def process_and_send_ads(context: ContextTypes.DEFAULT_TYPE, chat_id):
    ads = await fetch_divar_ads()
    new_count = 0
    
    # فقط 10 آگهی آخر را بررسی می‌کنیم (برای جلوگیری از ترافیک بالا روی آلبوم‌ها)
    for ad in reversed(ads[:10]):
        data = ad.get('data', {})
        token = data.get('token')
        
        if not token or token in seen_ads:
            continue
        
        # اطلاعات کلی
        title = data.get('title', 'بدون عنوان')
        price = data.get('middle_description_text', 'توافقی')
        district = data.get('district', 'نامشخص')
        desc = data.get('top_description_text', '')
        link = f"https://divar.ir/v/a/{token}"
        
        caption = (
            f"🏠 <b>{title}</b>\n"
            f"📍 محله: {district}\n"
            f"💰 {price}\n"
            f"📏 {desc}\n\n"
            f"🔗 <a href='{link}'>مشاهده و تماس</a>"
        )

        try:
            # دریافت آلبوم تصاویر (عملیات سنگین)
            # یک تاخیر کوچک برای جلوگیری از بن شدن
            await asyncio.sleep(1) 
            images = await get_ad_photos(token)
            
            if images and len(images) > 1:
                # ساخت مدیا گروپ برای آلبوم
                media_group = []
                # تلگرام اجازه میدهد تا 10 عکس در آلبوم باشد
                for i, img_url in enumerate(images[:5]): # محدود به 5 عکس برای سرعت
                    if i == 0:
                        # کپشن فقط روی عکس اول می‌آید
                        media_group.append(InputMediaPhoto(media=img_url, caption=caption, parse_mode='HTML'))
                    else:
                        media_group.append(InputMediaPhoto(media=img_url))
                
                await context.bot.send_media_group(chat_id=chat_id, media=media_group)
            
            elif images:
                # تک عکس
                await context.bot.send_photo(chat_id=chat_id, photo=images[0], caption=caption, parse_mode='HTML')
            else:
                # بدون عکس
                await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode='HTML', disable_web_page_preview=False)
            
            seen_ads.add(token)
            save_seen(seen_ads) # ذخیره فوری
            new_count += 1
            await asyncio.sleep(2) # استراحت بین ارسال پیام‌ها
            
        except BadRequest as e:
            logging.error(f"Bad Request (usually image format): {e}")
            # تلاش مجدد بدون عکس در صورت خرابی عکس
            await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode='HTML')
        except Exception as e:
            logging.error(f"General Send Error: {e}")

    return new_count

# --- دستورات ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 **ربات املاک دیوار کرج (نسخه پیشرفته)**\n\n"
        "**فیلتر قیمت:**\n`/min قیمت` | `/max قیمت`\n"
        "**فیلتر متراژ:**\n`/minarea متر` | `/maxarea متر`\n"
        "**فیلتر محله:**\n`/area نام_محله` (مثال: /area عظیمیه)\nبرای حذف محله: `/area clear`\n\n"
        "**امکانات:**\n`/parking` | `/elevator` | `/warehouse`\n\n"
        "🔍 `/update` - جستجوی دستی\n"
        "📊 `/status` - وضعیت تنظیمات"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def set_value(update, context, key, name):
    try:
        val = int(context.args[0])
        user_settings[key] = val
        save_settings(user_settings)
        await update.message.reply_text(f"✅ {name}: {val:,}")
    except:
        await update.message.reply_text("❌ لطفاً عدد وارد کنید.")

async def set_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ نام محله را بنویسید.\nمثال: /area عظیمیه")
        return
    
    query = " ".join(context.args)
    if query == "clear":
        user_settings["query"] = ""
        msg = "✅ فیلتر محله حذف شد (جستجوی کل کرج)."
    else:
        user_settings["query"] = query
        msg = f"✅ فیلتر روی محله: **{query}** تنظیم شد."
    
    save_settings(user_settings)
    await update.message.reply_text(msg, parse_mode='Markdown')

async def toggle_feature(update, context, key, name):
    user_settings[key] = not user_settings[key]
    save_settings(user_settings)
    state = "✅" if user_settings[key] else "❌"
    await update.message.reply_text(f"{name}: {state}")

async def status(update, context):
    s = user_settings
    q = s['query'] if s['query'] else "کل کرج"
    msg = (
        f"📊 **تنظیمات:**\n"
        f"📍 محله: {q}\n"
        f"💰 قیمت: {s['min_price']:,} تا {s['max_price']:,}\n"
        f"📏 متراژ: {s['min_area']} تا {s['max_area']}\n"
        f"🚗 پارکینگ: {'✅' if s['has_parking'] else '❌'}\n"
        f"🛗 آسانسور: {'✅' if s['has_elevator'] else '❌'}\n"
        f"📦 انباری: {'✅' if s['has_warehouse'] else '❌'}"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

# --- Main ---
if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    
    if not TOKEN: exit(1)
    app_bot = ApplicationBuilder().token(TOKEN).build()
    
    # هندلرها
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("update", lambda u,c: process_and_send_ads(c, u.effective_chat.id)))
    app_bot.add_handler(CommandHandler("min", lambda u,c: set_value(u,c, "min_price", "حداقل قیمت")))
    app_bot.add_handler(CommandHandler("max", lambda u,c: set_value(u,c, "max_price", "حداکثر قیمت")))
    app_bot.add_handler(CommandHandler("minarea", lambda u,c: set_value(u,c, "min_area", "حداقل متراژ")))
    app_bot.add_handler(CommandHandler("maxarea", lambda u,c: set_value(u,c, "max_area", "حداکثر متراژ")))
    app_bot.add_handler(CommandHandler("area", set_query))
    app_bot.add_handler(CommandHandler("parking", lambda u,c: toggle_feature(u,c,"has_parking","🅿️ پارکینگ")))
    app_bot.add_handler(CommandHandler("elevator", lambda u,c: toggle_feature(u,c,"has_elevator","🛗 آسانسور")))
    app_bot.add_handler(CommandHandler("warehouse", lambda u,c: toggle_feature(u,c,"has_warehouse","📦 انباری")))
    app_bot.add_handler(CommandHandler("status", status))

    # جاب خودکار
    app_bot.job_queue.run_repeating(lambda c: process_and_send_ads(c, CHAT_ID) if CHAT_ID else None, interval=3600, first=10)

    print("Advanced Bot Started...")
    app_bot.run_polling()
