import requests
import asyncio
import json
import os
import threading
from telegram import Bot
from datetime import datetime
from flask import Flask

# --- تنظیمات از Environment Variables خوانده می‌شوند ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

# تنظیمات دیوار
DIVAR_API_URL = "https://api.divar.ir/v8/web-search/karaj/buy-apartment"
CHECK_INTERVAL = 3600  # هر 1 ساعت

# فایل ذخیره موقت (توجه: در Render رایگان، فایل‌ها بعد از ریستارت پاک می‌شوند)
HISTORY_FILE = 'seen_ads.json'

app = Flask(__name__)

async def get_divar_ads():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Content-Type': 'application/json'
    }
    payload = {
        "json_schema": {
            "category": {"value": "buy-apartment"},
            "cities": ["karaj"],
        },
        "last-post-date": 0
    }
    try:
        response = requests.post(DIVAR_API_URL, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get('web_widgets', {}).get('post_list', [])
    except Exception as e:
        print(f"Error: {e}")
    return []

# تابع اصلی ربات
async def bot_loop():
    if not TELEGRAM_BOT_TOKEN or not CHAT_ID:
        print("Error: Token or Chat ID not found!")
        return

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    print("Bot started...")
    
    seen_ads = set()
    
    while True:
        print(f"Checking ads at {datetime.now()}...")
        ads = await get_divar_ads()
        
        # فقط 10 آگهی اول را بررسی می‌کنیم تا در شروع خیلی پیام نیاید
        current_batch = ads[:10] 
        
        for ad in reversed(current_batch):
            data = ad.get('data', {})
            token = data.get('token')
            
            if not token or token in seen_ads:
                continue
            
            title = data.get('title', 'بدون عنوان')
            price = data.get('middle_description_text', '')
            image_url = data.get('image_url')
            ad_link = f"https://divar.ir/v/a/{token}"
            
            caption = f"🏠 {title}\n💰 {price}\n🔗 {ad_link}"

            try:
                if image_url:
                    await bot.send_photo(chat_id=CHAT_ID, photo=image_url, caption=caption)
                else:
                    await bot.send_message(chat_id=CHAT_ID, text=caption)
                
                seen_ads.add(token)
                await asyncio.sleep(2)
            except Exception as e:
                print(f"Send Error: {e}")

        await asyncio.sleep(CHECK_INTERVAL)

# اجرای ربات در ترد جداگانه
def run_bot_process():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot_loop())

# روت وب‌سرور برای زنده نگه داشتن
@app.route('/')
def home():
    return "I am alive!", 200

if __name__ == '__main__':
    # اجرای ربات در پس‌زمینه
    t = threading.Thread(target=run_bot_process)
    t.start()
    
    # اجرای وب‌سرور روی پورتی که Render می‌دهد
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
