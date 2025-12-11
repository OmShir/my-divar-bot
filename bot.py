# Divar Smart Hunter - نسخه کامل با منوی دکمه (بدون نیاز به لینک)
# مخصوص Render.com - 24/7 - شخصی

import asyncio
import logging
import os
import sqlite3
import re
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

# تنظیمات
TOKEN = os.getenv("BOT_TOKEN", "8197183171:AAFyEyEA7NelgtU_ASMYWuDIyGhHuzEZ4KY")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}.onrender.com{WEBHOOK_PATH}"

logging.basicConfig(level=logging.INFO)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

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
    user_id INTEGER,
    city TEXT, district TEXT,
    deal_type TEXT,
    min_price INTEGER, max_price INTEGER,
    min_meter INTEGER, max_meter INTEGER,
    parking INTEGER, elevator INTEGER, warehouse INTEGER,
    url TEXT,
    last_token TEXT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS sent_ads (token TEXT PRIMARY KEY)''')
conn.commit()

# وضعیت‌ها
class AddFilter(StatesGroup):
    waiting_city = State()
    waiting_district = State()
    waiting_deal = State()
    waiting_price = State()
    waiting_meter = State()
    waiting_facilities = State()

# شهرها و مناطق
CITIES = {"تهران": "tehran", "مشهد": "mashhad", "اصفهان": "isfahan", "شیراز": "shiraz", "کرج": "karaj"}
TEHRAN_DISTRICTS = ["همه مناطق", "منطقه ۱", "منطقه ۲", "منطقه ۳", "منطقه ۴", "منطقه ۵", "منطقه ۶", "سعادت آباد", "ونک", "زعفرانیه", "نیاوران", "جردن", "الهیه", "شهرک غرب"]

# منوی اصلی
@router.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("جستجوی جدید", callback_data="new_filter")],
        [InlineKeyboardButton("فیلترهای من", callback_data="my_filters")],
        [InlineKeyboardButton("حذف همه", callback_data="clear_all")]
    ])
    await message.answer(
        "شکارچی هوشمند دیوار\n\n"
        "هر آگهی جدیدی که با شرایط دلخواهت ثبت بشه، زیر ۳۰ ثانیه برات میاد!\n\n"
        "دکمه زیر رو بزن و فیلتر بساز",
        reply_markup=kb
    )

@router.callback_query(F.data == "new_filter")
async def city_select(call: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(city, callback_data=f"city:{code}") for city, code in list(CITIES.items())[:3]],
        [InlineKeyboardButton(city, callback_data=f"city:{code}") for city, code in list(CITIES.items())[3:]]
    ])
    await call.message.edit_text("شهر رو انتخاب کن:", reply_markup=kb)
    await state.set_state(AddFilter.waiting_city)

@router.callback_query(F.data.startswith("city:"))
async def district_select(call: CallbackQuery, state: FSMContext):
    city_code = call.data.split(":")[1]
    await state.update_data(city=city_code)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(d, callback_data=f"dist:{d}") for d in TEHRAN_DISTRICTS[i:i+3]] for i in range(0, len(TEHRAN_DISTRICTS), 3)
    ])
    await call.message.edit_text("منطقه یا محله:", reply_markup=kb)
    await state.set_state(AddFilter.waiting_district)

@router.callback_query(F.data.startswith("dist:"))
async def deal_select(call: CallbackQuery, state: FSMContext):
    district = call.data.split(":", 1)[1]
    await state.update_data(district=district)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("خرید آپارتمان", callback_data="deal:buy-apartment")],
        [InlineKeyboardButton("رهن و اجاره", callback_data="deal:rent")],
        [InlineKeyboardButton("رهن کامل", callback_data="deal:full-rent")]
    ])
    await call.message.edit_text("نوع معامله:", reply_markup=kb)
    await state.set_state(AddFilter.waiting_deal)

@router.callback_query(F.data.startswith("deal:"))
async def price_select(call: CallbackQuery, state: FSMContext):
    deal = call.data.split(":")[1]
    await state.update_data(deal_type=deal)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("هر قیمتی", callback_data="price:any")],
        [InlineKeyboardButton("تا ۵ میلیارد", callback_data="price:0-5000000000")],
        [InlineKeyboardButton("۵-۱۰ میلیارد", callback_data="price:5000000000-10000000000")],
        [InlineKeyboardButton("۱۰-۲۰ میلیارد", callback_data="price:10000000000-20000000000")],
        [InlineKeyboardButton("بالای ۲۰ میلیارد", callback_data="price:20000000000-")]
    ])
    await call.message.edit_text("محدوده قیمت:", reply_markup=kb)
    await state.set_state(AddFilter.waiting_price)

@router.callback_query(F.data.startswith("price:"))
async def meter_select(call: CallbackQuery, state: FSMContext):
    price = call.data.split(":")[1]
    await state.update_data(price_range=price)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("هر متراژی", callback_data="meter:any")],
        [InlineKeyboardButton("۵۰-۸۰ متر", callback_data="meter:50-80")],
        [InlineKeyboardButton("۸۰-۱۲۰ متر", callback_data="meter:80-120")],
        [InlineKeyboardButton("۱۲۰-۲۰۰ متر", callback_data="meter:120-200")],
        [InlineKeyboardButton("بالای ۲۰۰ متر", callback_data="meter:200-")]
    ])
    await call.message.edit_text("متراژ:", reply_markup=kb)
    await state.set_state(AddFilter.waiting_meter)

@router.callback_query(F.data.startswith("meter:"))
async def facilities_select(call: CallbackQuery, state: FSMContext):
    meter = call.data.split(":")[1]
    await state.update_data(meter_range=meter)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("پارکینگ", callback_data="fac:parking:1"), InlineKeyboardButton("آسانسور", callback_data="fac:elevator:1")],
        [InlineKeyboardButton("انباری", callback_data="fac:warehouse:1")],
        [InlineKeyboardButton("تموم شد و ذخیره کن", callback_data="fac:done")]
    ])
    await call.message.edit_text("امکانات (اختیاری):", reply_markup=kb)
    await state.update_data(facilities={"parking":0, "elevator":0, "warehouse":0})
    await state.set_state(AddFilter.waiting_facilities)

@router.callback_query(F.data.startswith("fac:"))
async def save_new_filter(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    fac = data.get("facilities", {})
    part = call.data.split(":")
    
    if part[1] in ["parking", "elevator", "warehouse"]:
        fac[part[1]] = int(part[2])
        await state.update_data(facilities=fac)
        await call.answer("اضافه شد")
        return
    
    if part[1] == "done":
        # ساخت URL
        city = data["city"]
        deal = data["deal_type"]
        url = f"https://divar.ir/s/{city}/{deal}"
        params = []
        if data["district"] != "همه مناطق":
            params.append(f"districts={TEHRAN_DISTRICTS.index(data['district'])}")
        if data["price_range"] != "any":
            p = data["price_range"].split("-")
            params.append(f"price={p[0]}-{p[1] if len(p)>1 else ''}")
        if data["meter_range"] != "any":
            m = data["meter_range"].split("-")
            params.append(f"size={m[0]}-{m[1] if len(m)>1 else ''}")
        if params:
            url += "?" + "&".join(params)
        
        c.execute("""INSERT INTO filters (user_id, city, district, deal_type, min_price, max_price, min_meter, max_meter, parking, elevator, warehouse, url, last_token)
                     VALUES (?,?,?, ?,0,999999999999,0,9999, ?,?,?, ?,NULL)""",
                  (call.from_user.id, data["city"], data["district"], deal, fac.get("parking",0), fac.get("elevator",0), fac.get("warehouse",0), url))
        conn.commit()
        
        await call.message.edit_text(f"فیلتر با موفقیت ذخیره شد!\n\nاز این لحظه هر آگهی جدیدی که با این شرایط ثبت بشه، زیر ۳۰ ثانیه برات میاد\n\nپیش‌نمایش جستجو:\n{url}")
        await state.clear()

# نمایش فیلترها و حذف
@router.callback_query(F.data == "my_filters")
async def my_filters(call: CallbackQuery):
    c.execute("SELECT city, district, deal_type FROM filters WHERE user_id=?", (call.from_user.id,))
    rows = c.fetchall()
    if not rows:
        await call.message.edit_text("هنوز فیلتری نداری!")
        return
    text = "<b>فیلترهای فعال تو:</b>\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. {r[0].title()} - {r[1]} - {r[2].replace('-', ' ')}\n"
    await call.message.edit_text(text)

@router.callback_query(F.data == "clear_all")
async def clear_all(call: CallbackQuery):
    c.execute("DELETE FROM filters WHERE user_id=?", (call.from_user.id,))
    conn.commit()
    await call.message.edit_text("همه فیلترها پاک شد!")

# تابع چک کردن آگهی‌ها (هر ۲۵ ثانیه)
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
            except: pass
        await asyncio.sleep(25)

async def send_ad(token: str):
    url = f"https://divar.ir/v/{token}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200: return
            html = await resp.text()
    
    title = re.search(r'<h1[^>]*>(.*?)</h1>', html)
    title = title.group(1).strip() if title else "آگهی"
    price = re.search(r'kt-unexpandable-row__value[^>]*>(.*?)</p>', html)
    price = price.group(1).strip() if price else "توافقی"
    images = re.findall(r'[](https://s100.divar.ir/static/pictures/[^"]+)"', html)[:10]
    phone = re.search(r'tel:(\d+)', html)
    
    caption = f"آگهی جدید!\n\n<b>{title}</b>\nقیمت: {price}\n\n<a href='{url}'>مشاهده در دیوار</a>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton("باز کردن آگهی", url=url)]])
    if phone:
        kb.inline_keyboard.append([InlineKeyboardButton("تماس سریع", url=f"tel:{phone.group(1)}")])
    
    if images:
        media = [InputMediaPhoto(images[0], caption=caption)]
        for img in images[1:]: media.append(InputMediaPhoto(img))
        await bot.send_media_group(call.from_user.id, media)
        await bot.send_message(call.from_user.id, "دکمه‌ها:", reply_markup=kb)
    else:
        await bot.send_message(call.from_user.id, caption, reply_markup=kb, disable_web_page_preview=False)

# وب‌هوک
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)
    asyncio.create_task(checker())

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    app.on_startup.append(on_startup)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

if __name__ == "__main__":
    main()

