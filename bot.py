# Divar Smart Hunter - نسخه کامل با منوی دکمه (بدون لینک - فقط انتخاب فیلتر)
# آماده اجرا روی Render.com با webhook - 24/7
# تمام امکانات: شهر, منطقه, معامله, قیمت, متراژ, امکانات, چک خودکار, ارسال با عکس و تماس
# 2025

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
TOKEN = "8197183171:AAFyEyEA7NelgtU_ASMYWuDIyGhHuzEZ4KY"  # توکن خودت رو اینجا بذار
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'your-service-name.onrender.com')}{WEBHOOK_PATH}"
USER_ID = 48679788  # آیدی تلگرام خودت (از @userinfobot بگیر و اینجا بذار)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# دیتابیس
conn = sqlite3.connect("divar.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS filters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT,
    district TEXT,
    deal_type TEXT,
    min_price INTEGER DEFAULT 0,
    max_price INTEGER DEFAULT 999999999999,
    min_meter INTEGER DEFAULT 0,
    max_meter INTEGER DEFAULT 9999,
    parking INTEGER DEFAULT 0,
    elevator INTEGER DEFAULT 0,
    warehouse INTEGER DEFAULT 0,
    url TEXT,
    last_token TEXT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS sent_ads (token TEXT PRIMARY KEY)''')
conn.commit()

# وضعیت‌ها برای FSM
class AddFilter(StatesGroup):
    city = State()
    district = State()
    deal_type = State()
    price_min = State()
    price_max = State()
    meter_min = State()
    meter_max = State()
    facilities = State()

# لیست شهرها و مناطق (مثال برای تهران - می‌تونی اضافه کنی)
CITIES = [
    ("تهران", "tehran"),
    ("مشهد", "mashhad"),
    ("اصفهان", "isfahan"),
    ("شیراز", "shiraz"),
    ("کرج", "karaj")
]
TEHRAN_DISTRICTS = [
    ("همه مناطق", "all"),
    ("منطقه ۱", "1"),
    ("منطقه ۲", "2"),
    ("منطقه ۳", "3"),
    ("منطقه ۴", "4"),
    ("منطقه ۵", "5"),
    ("سعادت آباد", "saadatabad"),
    ("ونک", "vanak"),
    ("زعفرانیه", "zaferanieh"),
    ("نیاوران", "niavaran"),
    ("جردن", "jordan"),
    ("الهیه", "elahiieh"),
    # اضافه کن اگه نیاز داری
]

# منوی اصلی
@router.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("اضافه کردن فیلتر جدید", callback_data="add_filter")],
        [InlineKeyboardButton("فیلترهای من", callback_data="my_filters")],
        [InlineKeyboardButton("حذف همه فیلترها", callback_data="clear_all")],
        [InlineKeyboardButton("راهنما", callback_data="help")]
    ])
    await message.answer("🏠 <b>شکارچی هوشمند دیوار</b>\n\nبا دکمه‌ها فیلتر بساز و هر آگهی جدید رو زیر ۳۰ ثانیه دریافت کن!", reply_markup=kb)

@router.callback_query(F.data == "add_filter")
async def select_city(call: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(name, callback_data=f"city:{code}") for name, code in CITIES[i:i+2]] for i in range(0, len(CITIES), 2)
    ])
    await call.message.edit_text("شهر رو انتخاب کن:", reply_markup=kb)
    await state.set_state(AddFilter.city)

@router.callback_query(F.data.startswith("city:"))
async def select_district(call: CallbackQuery, state: FSMContext):
    city = call.data.split(":")[1]
    await state.update_data(city=city)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(name, callback_data=f"district:{code}") for name, code in TEHRAN_DISTRICTS[i:i+2]] for i in range(0, len(TEHRAN_DISTRICTS), 2)
    ])
    await call.message.edit_text("منطقه رو انتخاب کن:", reply_markup=kb)
    await state.set_state(AddFilter.district)

@router.callback_query(F.data.startswith("district:"))
async def select_deal_type(call: CallbackQuery, state: FSMContext):
    district = call.data.split(":")[1]
    await state.update_data(district=district)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("خرید آپارتمان", callback_data="deal:buy-apartment")],
        [InlineKeyboardButton("رهن و اجاره آپارتمان", callback_data="deal:rent-apartment")],
        [InlineKeyboardButton("رهن کامل", callback_data="deal:full-rent")]
    ])
    await call.message.edit_text("نوع معامله:", reply_markup=kb)
    await state.set_state(AddFilter.deal_type)

@router.callback_query(F.data.startswith("deal:"))
async def enter_price_min(call: CallbackQuery, state: FSMContext):
    deal = call.data.split(":")[1]
    await state.update_data(deal_type=deal)
    await call.message.edit_text("حداقل قیمت (تومان) رو وارد کن (یا 0 برای هر قیمتی):")
    await state.set_state(AddFilter.price_min)

@router.message(AddFilter.price_min)
async def enter_price_max(message: Message, state: FSMContext):
    min_price = int(message.text.strip()) if message.text.strip().isdigit() else 0
    await state.update_data(min_price=min_price)
    await message.answer("حداکثر قیمت (تومان) رو وارد کن (یا 0 برای هر قیمتی):")
    await state.set_state(AddFilter.price_max)

@router.message(AddFilter.price_max)
async def enter_meter_min(message: Message, state: FSMContext):
    max_price = int(message.text.strip()) if message.text.strip().isdigit() else 999999999999
    await state.update_data(max_price=max_price)
    await message.answer("حداقل متراژ رو وارد کن (یا 0 برای هر متراژی):")
    await state.set_state(AddFilter.meter_min)

@router.message(AddFilter.meter_min)
async def enter_meter_max(message: Message, state: FSMContext):
    min_meter = int(message.text.strip()) if message.text.strip().isdigit() else 0
    await state.update_data(min_meter=min_meter)
    await message.answer("حداکثر متراژ رو وارد کن (یا 0 برای هر متراژی):")
    await state.set_state(AddFilter.meter_max)

@router.message(AddFilter.meter_max)
async def select_facilities(message: Message, state: FSMContext):
    max_meter = int(message.text.strip()) if message.text.strip().isdigit() else 9999
    await state.update_data(max_meter=max_meter)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("پارکینگ ✓", callback_data="fac:parking")],
        [InlineKeyboardButton("آسانسور ✓", callback_data="fac:elevator")],
        [InlineKeyboardButton("انباری ✓", callback_data="fac:warehouse")],
        [InlineKeyboardButton("تموم و ذخیره کن ✅", callback_data="fac:done")]
    ])
    await message.answer("امکانات دلخواه (اختیاری - می‌تونی چند تا انتخاب کنی):", reply_markup=kb)
    await state.update_data(parking=0, elevator=0, warehouse=0)
    await state.set_state(AddFilter.facilities)

@router.callback_query(F.data.startswith("fac:"))
async def save_filter(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if call.data == "fac:parking":
        await state.update_data(parking=1)
        await call.answer("پارکینگ اضافه شد")
    elif call.data == "fac:elevator":
        await state.update_data(elevator=1)
        await call.answer("آسانسور اضافه شد")
    elif call.data == "fac:warehouse":
        await state.update_data(warehouse=1)
        await call.answer("انباری اضافه شد")
    elif call.data == "fac:done":
        # ساخت URL
        base = f"https://divar.ir/s/{data['city']}/{data['deal_type']}"
        params = []
        if data['district'] != "all":
            params.append(f"districts={data['district']}")
        if data['min_price'] > 0 or data['max_price'] < 999999999999:
            params.append(f"price={data['min_price']}-{data['max_price']}")
        if data['min_meter'] > 0 or data['max_meter'] < 9999:
            params.append(f"size={data['min_meter']}-{data['max_meter']}")
        url = base + ("?" + "&".join(params) if params else "")

        c.execute('''INSERT INTO filters (city, district, deal_type, min_price, max_price, min_meter, max_meter, parking, elevator, warehouse, url)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (data['city'], data['district'], data['deal_type'], data['min_price'], data['max_price'], data['min_meter'], data['max_meter'], data.get('parking'), data.get('elevator'), data.get('warehouse'), url))
        conn.commit()
        await call.message.edit_text(f"فیلتر ذخیره شد!\nURL ساخته‌شده: {url}\n\nهر آگهی جدید برات میاد!")
        await state.clear()

@router.callback_query(F.data == "my_filters")
async def my_filters(call: CallbackQuery):
    c.execute("SELECT url FROM filters")
    rows = c.fetchall()
    text = "<b>فیلترهای فعال:</b>\n\n"
    for i, (url,) in enumerate(rows, 1):
        text += f"{i}. {url}\n"
    await call.message.edit_text(text or "هیچ فیلتری نداری!")

@router.callback_query(F.data == "clear_all")
async def clear_all(call: CallbackQuery):
    c.execute("DELETE FROM filters")
    c.execute("DELETE FROM sent_ads")
    conn.commit()
    await call.message.edit_text("همه پاک شد!")

@router.callback_query(F.data == "help")
async def help_cmd(call: CallbackQuery):
    await call.message.edit_text("راهنما:\n\nدکمه 'اضافه کردن فیلتر جدید' رو بزن\nشهر، منطقه، معامله، قیمت، متراژ و امکانات رو انتخاب کن\nربات خودش URL رو می‌سازه و هر آگهی جدید رو می‌فرسته!")

# تابع چک و ارسال (بقیه کد مثل قبلی)
async def checker():
    while True:
        c.execute("SELECT url, last_token FROM filters")
        for url, last_token in c.fetchall():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200: continue
                        html = await resp.text()
                tokens = re.findall(r'data-token="([a-zA-Z0-9]{20,})"', html)[:10]
                for token in tokens:
                    if token not in [r[0] for r in c.execute("SELECT token FROM sent_ads")]:
                        await send_ad(token)
                        c.execute("INSERT INTO sent_ads VALUES (?)", (token,))
                        conn.commit()
                if tokens:
                    c.execute("UPDATE filters SET last_token=? WHERE url=?", (tokens[0], url))
                    conn.commit()
            except Exception as e:
                logging.error(e)
        await asyncio.sleep(25)

async def send_ad(token: str):
    url = f"https://divar.ir/v/{token}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200: return
            html = await resp.text()

    title = re.search(r'<h1[^>]*>(.*?)</h1>', html)
    title = title.group(1).strip() if title else "آگهی بدون عنوان"
    price = re.search(r'kt-unexpandable-row__value[^>]*>(.*?)</p>', html)
    price = price.group(1).strip() if price else "توافقی"
    desc = re.search(r'kt-description-row__text[^>]*>(.*?)</p>', html, re.S)
    desc = desc.group(1).strip().replace("<br>", "\n")[:300] + "..." if desc else ""
    phone = re.search(r'tel:(\d+)', html)
    phone_url = f"tel:{phone.group(1)}" if phone else None
    images = re.findall(r'"(https://s100.divar.ir/static/pictures/[^"]+)"', html)[:10]

    text = f"🏠 <b>{title}</b>\n💰 {price}\n📝 {desc}\n\n<a href='{url}'>مشاهده در دیوار</a>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("باز کردن آگهی 🚪", url=url)]
    ])
    if phone_url:
        kb.inline_keyboard.append([InlineKeyboardButton("تماس سریع ☎️", url=phone_url)])

    if images:
        media = [InputMediaPhoto(images[0], caption=text)]
        for img in images[1:]:
            media.append(InputMediaPhoto(img))
        await bot.send_media_group(USER_ID, media)
        await bot.send_message(USER_ID, "دکمه‌ها:", reply_markup=kb)
    else:
        await bot.send_message(USER_ID, text, reply_markup=kb, disable_web_page_preview=False)

# وب‌هوک و استارت
async def on_startup(app):
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)
    logging.info("Webhook set!")
    asyncio.create_task(checker())

if __name__ == "__main__":
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    app.on_startup.append(on_startup)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

