import logging
import asyncio
import json
import os
import requests
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# --- تنظیمات اولیه ---
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')  # آیدی عددی شما به عنوان ادمین پیش‌فرض

# تنظیمات پیش‌فرض فیلترها
DEFAULT_SETTINGS = {
    "min_price": 0,          # 0 یعنی بدون محدودیت
    "max_price": 0,          # 0 یعنی بدون محدودیت
    "last_check_time": 0
}

# متغیر برای ذخیره تنظیمات در حافظه (در رندر رایگان با ریستارت پاک می‌شود)
user_settings = DEFAULT_SETTINGS.copy()
seen_ads = set()

# راه اندازی لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- وب‌سرور Flask (برای زنده نگه داشتن در Render) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running...", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- توابع مربوط به دیوار ---
async def fetch_divar_ads():
    """دریافت آگهی‌ها با اعمال فیلترهای کاربر"""
    url = "https://api.divar.ir/v8/web-search/karaj/buy-apartment"
    
    json_schema = {
        "category": {"value": "buy-apartment"},
        "cities": ["karaj"],
    }

    # اعمال فیلتر قیمت اگر تنظیم شده باشد
    price_filter = {}
    if user_settings["min_price"] > 0:
        price_filter["min"] = user_settings["min_price"]
    if user_settings["max_price"] > 0:
        price_filter["max"] = user_settings["max_price"]
    
    if price_filter:
        json_schema["price"] = price_filter

    payload = {
        "json_schema": json_schema,
        "last-post-date": 0
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get('web_widgets', {}).get('post_list', [])
    except Exception as e:
        logging.error(f"Divar API Error: {e}")
    return []

async def process_and_send_ads(context: ContextTypes.DEFAULT_TYPE, chat_id):
    """پردازش و ارسال آگهی‌ها"""
    ads = await fetch_divar_ads()
    
    # فقط 20 آگهی آخر را بررسی می‌کنیم
    new_count = 0
    for ad in reversed(ads[:20]):
        data = ad.get('data', {})
        token = data.get('token')
        
        if not token or token in seen_ads:
            continue
        
        title = data.get('title', 'بدون عنوان')
        price = data.get('middle_description_text', 'توافقی')
        desc = data.get('top_description_text', '')
        image_url = data.get('image_url')
        link = f"https://divar.ir/v/a/{token}"
        
        caption = (
            f"🏠 <b>{title}</b>\n"
            f"💰 قیمت: {price}\n"
            f"📍 {desc}\n\n"
            f"🔗 <a href='{link}'>مشاهده و تماس</a>"
        )
        
        try:
            if image_url:
                await context.bot.send_photo(chat_id=chat_id, photo=image_url, caption=caption, parse_mode='HTML')
            else:
                await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode='HTML', disable_web_page_preview=False)
            
            seen_ads.add(token)
            new_count += 1
            await asyncio.sleep(1.5) # جلوگیری از اسپم
            
        except Exception as e:
            logging.error(f"Send Error: {e}")
            
    return new_count

# --- دستورات ربات ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور شروع"""
    msg = (
        "🤖 ربات دیوار کرج فعال شد!\n\n"
        "دستورات:\n"
        "🔄 /update - بررسی دستی آگهی‌های جدید\n"
        "⬇️ /min قیمت - تعیین حداقل قیمت (تومان)\n"
        "⬆️ /max قیمت - تعیین حداکثر قیمت (تومان)\n"
        "ℹ️ /status - وضعیت فعلی فیلترها"
    )
    await update.message.reply_text(msg)

async def manual_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آپدیت دستی توسط کاربر"""
    await update.message.reply_text("🔄 در حال بررسی آگهی‌های جدید...")
    count = await process_and_send_ads(context, update.effective_chat.id)
    
    if count == 0:
        await update.message.reply_text("✅ آگهی جدیدی یافت نشد.")
    else:
        await update.message.reply_text(f"✅ {count} آگهی جدید ارسال شد.")

async def set_min_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم حداقل قیمت"""
    try:
        price = int(context.args[0])
        user_settings['min_price'] = price
        await update.message.reply_text(f"✅ حداقل قیمت روی {price:,} تومان تنظیم شد.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ لطفاً قیمت را به عدد وارد کنید.\nمثال: /min 2000000000")

async def set_max_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم حداکثر قیمت"""
    try:
        price = int(context.args[0])
        user_settings['max_price'] = price
        await update.message.reply_text(f"✅ حداکثر قیمت روی {price:,} تومان تنظیم شد.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ لطفاً قیمت را به عدد وارد کنید.\nمثال: /max 5000000000")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش وضعیت فیلترها"""
    min_p = f"{user_settings['min_price']:,}" if user_settings['min_price'] > 0 else "نامحدود"
    max_p = f"{user_settings['max_price']:,}" if user_settings['max_price'] > 0 else "نامحدود"
    
    msg = (
        "📊 **تنظیمات فعلی:**\n\n"
        f"⬇️ حداقل قیمت: {min_p} تومان\n"
        f"⬆️ حداکثر قیمت: {max_p} تومان\n"
        f"🏙 شهر: کرج\n"
        f"📂 دسته‌بندی: فروش آپارتمان"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

# --- جاب (Job) خودکار ---
async def scheduled_check(context: ContextTypes.DEFAULT_TYPE):
    """این تابع هر ساعت اجرا می‌شود"""
    if CHAT_ID:
        logging.info("Running scheduled check...")
        await process_and_send_ads(context, CHAT_ID)

# --- تابع اصلی ---
if __name__ == '__main__':
    # اجرای Flask در یک ترد جداگانه
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # تنظیمات ربات تلگرام
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN is missing!")
        exit(1)

    application = ApplicationBuilder().token(TOKEN).build()

    # اضافه کردن هندلرها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("update", manual_check))
    application.add_handler(CommandHandler("min", set_min_price))
    application.add_handler(CommandHandler("max", set_max_price))
    application.add_handler(CommandHandler("status", status))

    # تنظیم جاب خودکار (هر 3600 ثانیه = 1 ساعت)
    job_queue = application.job_queue
    job_queue.run_repeating(scheduled_check, interval=3600, first=10)

    print("Bot is polling...")
    application.run_polling()
