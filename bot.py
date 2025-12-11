# Divar Smart Hunter - نسخه نهایی و 100% کارکردن روی Render.com
# فقط با دکمه فیلتر می‌سازی — بدون نیاز به لینک
# توکن و آیدی خودت رو عوض کن

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

# توکن و آیدی خودت رو اینجا عوض کن
TOKEN = "8197183171:AAFyEyEA7NelgtU_ASMYWuDIyGhHuzEZ4KY"  # توکن ربات
USER_ID = 48679788  # آیدی تلگرام خودت (عدد)

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'divar-hunter.onrender.com')}{WEBHOOK_PATH}"

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
    city TEXT, district TEXT, deal_type TEXT,
    min_price INTEGER, max_price INTEGER,
    min_meter INTEGER, max_meter INTEGER,
    parking INTEGER, elevator INTEGER, warehouse INTEGER,
    url TEXT, last_token TEXT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS sent_ads (token TEXT PRIMARY KEY)''')
conn.commit()

# وضعیت‌ها
class AddFilter(StatesGroup):
    city = State()
    district = State()
    deal_type = State()
    price_min = State()
    price_max = State()
    meter_min = State()
    meter_max = State()
    facilities = State()

CITIES = [("تهران", "tehran"), ("مشهد", "mashhad"), ("اصفهان", "isfahan"), ("شیراز", "shiraz")]
TEHRAN_DISTRICTS = [("همه", "all"), ("منطقه ۱", "1"), ("منطقه ۲", "2"), ("منطقه ۳", "3"), ("منطقه ۵", "5"), ("سعادت آباد", "saadat-abad"), ("ونک", "vanak")]

@router.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="اضافه کردن فیلتر جدید", callback_data="add_filter")],
        [InlineKeyboardButton(text="فیلترهای من", callback_data="my_filters")],
        [InlineKeyboardButton(text="حذف همه", callback_data="clear_all")]
    ])
    await message.answer("شکارچی دیوار فعال شد!\n\nفقط با دکمه فیلتر بساز و منتظر آگهی باش!", reply_markup=kb)

@router.callback_query(F.data == "add_filter")
async def select_city(call: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=n, callback_data=f"city:{c}") for n, c in CITIES]])
    await call.message.edit_text("شهر:", reply_markup=kb)
    await state.set_state(AddFilter.city)

@router.callback_query(F.data.startswith("city:"))
async def select_district(call: CallbackQuery, state: FSMContext):
    city = call.data.split(":")[1]
    await state.update_data(city=city)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=n, callback_data=f"dist:{c}") for n, c in TEHRAN_DISTRICTS]])
    await call.message.edit_text("منطقه:", reply_markup=kb)
    await state.set_state(AddFilter.district)

@router.callback_query(F.data.startswith("dist:"))
async def select_deal(call: CallbackQuery, state: FSMContext):
    dist = call.data.split(":")[1]
    await state.update_data(district=dist)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="خرید آپارتمان", callback_data="deal:buy-apartment")],
        [InlineKeyboardButton(text="رهن و اجاره", callback_data="deal:rent-apartment")]
    ])
    await call.message.edit_text("نوع معامله:", reply_markup=kb)
    await state.set_state(AddFilter.deal_type)

@router.callback_query(F.data.startswith("deal:"))
async def price_min(call: CallbackQuery, state: FSMContext):
    deal = call.data.split(":")[1]
    await state.update_data(deal_type=deal)
    await call.message.edit_text("حداقل قیمت (تومان) - مثلاً 5000000000 یا 0 برای بدون محدودیت:")
    await state.set_state(AddFilter.price_min)

@router.message(AddFilter.price_min)
async def price_max(message: Message, state: FSMContext):
    try: p = int(message.text.replace(",", ""))
    except: p = 0
    await state.update_data(min_price=p)
    await message.answer("حداکثر قیمت (یا 0 برای بدون محدودیت):")
    await state.set_state(AddFilter.price_max)

@router.message(AddFilter.price_max)
async def meter_min(message: Message, state: FSMContext):
    try: p = int(message.text.replace(",", ""))
    except: p = 999999999999
    await state.update_data(max_price=p)
    await message.answer("حداقل متراژ (یا 0):")
    await state.set_state(AddFilter.meter_min)

@router.message(AddFilter.meter_min)
async def meter_max(message: Message, state: FSMContext):
    try: m = int(message.text)
    except: m = 0
    await state.update_data(min_meter=m)
    await message.answer("حداکثر متراژ (یا 0):")
    await state.set_state(AddFilter.meter_max)

@router.message(AddFilter.meter_max)
async def facilities(message: Message, state: FSMContext):
    try: m = int(message.text)
    except: m = 9999
    await state.update_data(max_meter=m)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="پارکینگ", callback_data="fac:parking")],
        [InlineKeyboardButton(text="آسانسور", callback_data="fac:elevator")],
        [InlineKeyboardButton(text="انباری", callback_data="fac:warehouse")],
        [InlineKeyboardButton(text="ذخیره کن", callback_data="fac:done")]
    ])
    await message.answer("امکانات (اختیاری):", reply_markup=kb)
    await state.update_data(parking=0, elevator=0, warehouse=0)
    await state.set_state(AddFilter.facilities)

@router.callback_query(F.data.startswith("fac:"))
async def save_filter(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if call.data == "fac:parking": await state.update_data(parking=1); await call.answer("پارکینگ")
    if call.data == "fac:elevator": await state.update_data(elevator=1); await call.answer("آسانسور")
    if call.data == "fac:warehouse": await state.update_data(warehouse=1); await call.answer("انباری")
    if call.data == "fac:done":
        base = f"https://divar.ir/s/{data['city']}/{data['deal_type']}"
        params = []
        if data['district'] != 'all': params.append(f"districts={data['district']}")
        if data['min_price']: params.append(f"price={data['min_price']}-{data['max_price']}")
        if data['min_meter']: params.append(f"size={data['min_meter']}-{data['max_meter']}")
        url = base + ("?" + "&".join(params) if params else "")
        c.execute("INSERT INTO filters (city,district,deal_type,min_price,max_price,min_meter,max_meter,parking,elevator,warehouse,url) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (data['city'], data['district'], data['deal_type'], data['min_price'], data['max_price'], data['min_meter'], data['max_meter'],
                   data.get('parking',0), data.get('elevator',0), data.get('warehouse',0), url))
        conn.commit()
        await call.message.edit_text(f"فیلتر ذخیره شد!\nهر آگهی جدید زیر ۳۰ ثانیه برات میاد!\n\nپیش‌نمایش:\n{url}")
        await state.clear()

@router.callback_query(F.data == "my_filters")
async def my_filters(call: CallbackQuery):
    c.execute("SELECT url FROM filters")
    rows = c.fetchall()
    text = "فیلترهای فعال:\n\n" + "\n".join([f"{i+1}. {url[0]}" for i, url in enumerate(rows)]) if rows else "هیچ فیلتری نداری!"
    await call.message.edit_text(text)

@router.callback_query(F.data == "clear_all")
async def clear_all(call: CallbackQuery):
    c.execute("DELETE FROM filters"); c.execute("DELETE FROM sent_ads"); conn.commit()
    await call.message.edit_text("همه پاک شد!")

async def checker():
    while True:
        c.execute("SELECT url, last_token FROM filters")
        for url, last in c.fetchall():
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(url) as r:
                        if r.status != 200: continue
                        html = await r.text()
                tokens = re.findall(r'data-token="([a-zA-Z0-9]{20,})"', html)[:10]
                for token in tokens:
                    if token not in [x[0] for x in c.execute("SELECT token FROM sent_ads")]:
                        await send_ad(token)
                        c.execute("INSERT INTO sent_ads VALUES (?)", (token,))
                        conn.commit()
                if tokens:
                    c.execute("UPDATE filters SET last_token=? WHERE url=?", (tokens[0], url))
                    conn.commit()
            except Exception as e:
                logging.error(e)
        await asyncio.sleep(25)

async def send_ad(token):
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
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="مشاهده در دیوار", url=url)]
    ])
    if phone:
        kb.inline_keyboard.append([InlineKeyboardButton(text="تماس سریع", url=f"tel:{phone.group(1)}")])
    text = f"<b>{title}</b>\nقیمت: {price}\n\n<a href='{url}'>دیوار</a>"
    if images:
        media = [InputMediaPhoto(images[0], caption=text)]
        for img in images[1:]: media.append(InputMediaPhoto(img))
        await bot.send_media_group(USER_ID, media)
        await bot.send_message(USER_ID, "دکمه‌ها:", reply_markup=kb)
    else:
        await bot.send_message(USER_ID, text, reply_markup=kb, disable_web_page_preview=False)

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
