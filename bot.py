# MyDivarHunterBot - نسخه webhook برای Render (aiogram 3.x)
# شخصی و رایگان - 2025

import asyncio
import aiohttp
import re
import sqlite3
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.filters import CommandStart
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# ========== تنظیمات ==========
TOKEN = os.getenv("TOKEN", "8197183171:AAFyEyEA7NelgtU_ASMYWuDIyGhHuzEZ4KY")  # توکن از Environment Variable (بهتره)
WEBHOOK_URL = f"https://{os.getenv('RENDER_SERVICE_NAME', 'your-service')}.onrender.com/webhook"  # Render URL خودت
WEBHOOK_PATH = f"/webhook/{TOKEN}"
# ==============================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# دیتابیس
conn = sqlite3.connect('my_divar.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS filters 
             (id INTEGER PRIMARY KEY, name TEXT, url TEXT, last_token TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS sent_ads (token TEXT PRIMARY KEY)''')
conn.commit()

def load_filters():
    c.execute("SELECT name, url, last_token FROM filters")
    return [{"name": row[0], "url": row[1], "last_token": row[2]} for row in c.fetchall()]

filters = load_filters()
sent_ads = {row[0] for row in c.execute("SELECT token FROM sent_ads").fetchall()}

# روترها
@router.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ اضافه کردن فیلتر", callback_data="add"),
            InlineKeyboardButton(text="📋 فیلترهای من", callback_data="list")
        ],
        [
            InlineKeyboardButton(text="🗑 حذف همه", callback_data="clear"),
            InlineKeyboardButton(text="ℹ️ راهنما", callback_data="help")
        ]
    ])
    await message.answer(
        "🏠 <b>شکارچی شخصی دیوار</b>\n\n"
        "هر خونه جدیدی که با فیلترهات جور دربیاد، زیر ۳۰ ثانیه برات میاد!\n"
        f"فیلتر فعال: <b>{len(filters)}</b> تا",
        reply_markup=kb,
        parse_mode="HTML"
    )

@router.callback_query(F.data == "add")
async def add_filter(callback):
    await callback.message.answer(
        "لینک جستجوی دیوار رو برام بفرست:\n\n"
        "مثال:\n"
        "https://divar.ir/s/tehran/buy-apartment?price=5000000000-15000000000"
    )
    await callback.answer()

@router.message(F.text)
async def save_filter(message: Message):
    url = message.text.strip()
    if "divar.ir" not in url:
        await message.answer("❌ لینک معتبر دیوار نیست!")
        return

    name = url.split("/")[-1].replace("-", " ").replace("?", "").title() or f"فیلتر {len(filters)+1}"

    c.execute("INSERT INTO filters (name, url) VALUES (?, ?)", (name, url))
    conn.commit()
    filters.append({"name": name, "url": url, "last_token": None})
    
    await message.answer(f"✅ فیلتر اضافه شد:\n<b>{name}</b>\nحالا هر آگهی جدیدی بیاد برات میفرستم!", parse_mode="HTML")

@router.callback_query(F.data == "list")
async def list_filters(callback):
    if not filters:
        await callback.message.answer("هنوز فیلتری نداری!")
        return
    text = "<b>فیلترهای فعال:</b>\n\n"
    for i, f in enumerate(filters, 1):
        text += f"{i}. {f['name']}\n"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "clear")
async def clear_filters(callback):
    c.execute("DELETE FROM filters")
    c.execute("DELETE FROM sent_ads")
    conn.commit()
    filters.clear()
    sent_ads.clear()
    await callback.message.answer("🗑 همه چیز پاک شد!")
    await callback.answer()

@router.callback_query(F.data == "help")
async def help_cmd(callback):
    await callback.message.answer(
        "راهنما:\n\n"
        "1️⃣ برو دیوار → جستجو کن (منطقه، قیمت، متراژ و ...)\n"
        "2️⃣ لینک بالای مرورگر رو کپی کن\n"
        "3️⃣ اینجا بفرست\n"
        "4️⃣ تموم! هر آگهی جدید زیر ۳۰ ثانیه برات میاد!\n\n"
        "هر ۲۰ ثانیه یکبار چک می‌کنم 🔥"
    )
    await callback.answer()

# تابع چک آگهی‌ها (background task)
async def checker():
    while True:
        for filt in filters:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                    async with session.get(filt["url"]) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text()

                tokens = re.findall(r'data-token="([a-zA-Z0-9]{20,})"', html)[:8]

                for token in tokens:
                    if token not in sent_ads and token != filt.get("last_token"):
                        await send_ad(token, filt["name"])
                        sent_ads.add(token)
                        c.execute("INSERT OR IGNORE INTO sent_ads VALUES (?)", (token,))
                        conn.commit()

                if tokens:
                    filt["last_token"] = tokens[0]
                    c.execute("UPDATE filters SET last_token=? WHERE url=?", (tokens[0], filt["url"]))
                    conn.commit()

            except Exception as e:
                logger.error(f"Error in checker: {e}")
        
        await asyncio.sleep(20)  # هر ۲۰ ثانیه

async def send_ad(token: str, filter_name: str):
    url = f"https://divar.ir/v/{token}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return
                html = await resp.text()

        title = re.search(r'<h1[^>]*>(.*?)</h1>', html)
        title = title.group(1).strip() if title else "آگهی بدون عنوان"

        price = re.search(r'kt-unexpandable-row__value[^>]*>(.*?)</p>', html)
        price = price.group(1).strip() if price else "توافقی"

        desc = re.search(r'kt-description-row__text[^>]*>(.*?)</p>', html, re.S)
        desc = (desc.group(1).strip().replace("<br>", "\n")[:300] + "..." if desc else "")

        phone = re.search(r'tel:(\d+)', html)
        phone_url = f"tel:{phone.group(1)}" if phone else None

        images = re.findall(r'[](https://s100.divar.ir/static/pictures/[^"]+)"', html)[:10]

        caption = f"🏠 <b>آگهی جدید!</b>\n\n" \
                  f"<b>{title}</b>\n" \
                  f"💰 {price}\n" \
                  f"📍 فیلتر: {filter_name}\n\n" \
                  f"{desc}\n\n" \
                  f"<a href='{url}'>مشاهده در دیوار</a>"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="باز کردن آگهی", url=url)]
        ])
        if phone_url:
            kb.inline_keyboard.append([InlineKeyboardButton(text="تماس سریع ☎", url=phone_url)])

        chat_id = (await bot.get_me()).id  # به خودت می‌فرسته (یا user_id ثابت بذار)
        if images:
            media = [InputMediaPhoto(images[0], caption=caption, parse_mode="HTML")]
            for img in images[1:]:
                media.append(InputMediaPhoto(img))
            await bot.send_media_group(chat_id, media)
            await bot.send_message(chat_id, "دکمه‌ها:", reply_markup=kb)
        else:
            await bot.send_message(chat_id, caption, reply_markup=kb, disable_web_page_preview=False, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error sending ad: {e}")

# Webhook handler
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL + WEBHOOK_PATH)
    logger.info("Webhook set!")
    asyncio.create_task(checker())  # شروع checker

async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("Bot stopped!")

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    port = int(os.environ.get("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
