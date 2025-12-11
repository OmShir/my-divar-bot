# bot.py - نسخه نهایی و کاملاً کارکردن روی Render.com
import asyncio
import logging
import os
import sqlite3
import re
import aiohttp
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

# تنظیمات
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}.onrender.com{WEBHOOK_PATH}"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# دیتابیس
conn = sqlite3.connect("divar.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS filters (id INTEGER PRIMARY KEY, user_id INTEGER, url TEXT, last_token TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS sent_ads (token TEXT PRIMARY KEY)''')
conn.commit()

class AddFilter(StatesGroup):
    waiting_url = State()

@router.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("جستجوی جدید", callback_data="new_filter")],
        [InlineKeyboardButton("فیلترهای من", callback_data="list_filters")],
        [InlineKeyboardButton("حذف همه", callback_data="clear_all")]
    ])
    await message.answer(
        "شکارچی دیوار فعال شد!\n\n"
        "هر آگهی جدیدی که با فیلترهات جور باشه، زیر ۳۰ ثانیه برات میاد\n\n"
        "دکمه بزن و فیلتر بساز",
        reply_markup=kb
    )

@router.callback_query(F.data == "new_filter")
async def new_filter(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("لینک جستجوی دیوار رو بفرست (همون لینکی که تو مرورگر باز کردی):")
    await state.set_state(AddFilter.waiting_url)

@router.message(AddFilter.waiting_url)
async def save_filter(message: Message, state: FSMContext):
    url = message.text.strip()
    if "divar.ir" not in url:
        await message.answer("لینک معتبر دیوار نیست!")
        return
    c.execute("INSERT INTO filters (user_id, url) VALUES (?, ?)", (message.from_user.id, url))
    conn.commit()
    await message.answer(f"فیلتر ذخیره شد!\nاز این به بعد هر آگهی جدیدی بیاد، برات می‌فرستم\n\nپیش‌نمایش:\n{url}")
    await state.clear()

@router.callback_query(F.data == "list_filters")
async def list_filters(call: CallbackQuery):
    c.execute("SELECT url FROM filters WHERE user_id=?", (call.from_user.id,))
    rows = c.fetchall()
    if not rows:
        await call.message.edit_text("فیلتری نداری!")
        return
    text = "فیلترهای فعال:\n\n"
    for i, (url,) in enumerate(rows, 1):
        text += f"{i}. {url}\n"
    await call.message.edit_text(text)

@router.callback_query(F.data == "clear_all")
async def clear_all(call: CallbackQuery):
    c.execute("DELETE FROM filters WHERE user_id=?", (call.from_user.id,))
    c.execute("DELETE FROM sent_ads")
    conn.commit()
    await call.message.edit_text("همه پاک شد!")

# چک کردن آگهی‌ها
async def checker():
    while True:
        c.execute("SELECT url, last_token FROM filters")
        for url, last_token in c.fetchall():
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(url) as r:
                        if r.status != 200: continue
                        html = await r.text()
                tokens = re.findall(r'data-token="([a-zA-Z0-9]{20,})"', html)[:10]
                for token in tokens:
                    if token not in [row[0] for row in c.execute("SELECT token FROM sent_ads")]:
                        await send_ad(token, url)
                        c.execute("INSERT INTO sent_ads VALUES (?)", (token,))
                        conn.commit()
                if tokens:
                    c.execute("UPDATE filters SET last_token=? WHERE url=?", (tokens[0], url))
                    conn.commit()
            except: pass
        await asyncio.sleep(25)

async def send_ad(token: str, filter_url: str):
    url = f"https://divar.ir/v/{token}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            if r.status != 200: return
            html = await r.text()
    
    title = re.search(r'<h1[^>]*>(.*?)</h1>', html)
    title = title.group(1).strip() if title else "آگهی"
    price = re.search(r'kt-unexpandable-row__value[^>]*>(.*?)</p>', html)
    price = price.group(1).strip() if price else "توافقی"
    images = re.findall(r'[](https://s100.divar.ir/static/pictures/[^"]+)"', html)[:10]
    phone = re.search(r'tel:(\d+)', html)

    caption = f"آگهی جدید!\n\n<b>{title}</b>\nقیمت: {price}\n\n<a href='{url}'>مشاهده در دیوار</a>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton("باز کردن", url=url)]])
    if phone:
        kb.inline_keyboard.append([InlineKeyboardButton("تماس", url=f"tel:{phone.group(1)}")])

    user_id = 8197183171  # آیدی خودت (از @userinfobot بگیر و اینجا بذار)
    if images:
        media = [InputMediaPhoto(i, caption=caption if j==0 else "") for j, i in enumerate(images)]
        await bot.send_media_group(user_id, media)
        await bot.send_message(user_id, "دکمه‌ها:", reply_markup=kb)
    else:
        await bot.send_message(user_id, caption, reply_markup=kb, disable_web_page_preview=False)

# وب‌هوک
async def on_startup(app):
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook set to: {WEBHOOK_URL}")
    asyncio.create_task(checker())

app = web.Application()
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
app.on_startup.append(on_startup)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
