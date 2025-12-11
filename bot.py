# MyDivarHunterBot - نسخه شخصی کامل (بدون محدودیت، بدون پرمیوم)
# فقط برای خودت - 2025

import asyncio
import aiohttp
import re
import sqlite3
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto

# ========== تنظیمات ==========
TOKEN = "8197183171:AAFyEyEA7NelgtU_ASMYWuDIyGhHuzEZ4KY"  # از @BotFather بگیر و اینجا بذار
# ==============================

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

# دیتابیس ساده و دائمی
conn = sqlite3.connect('my_divar.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS filters 
             (id INTEGER PRIMARY KEY, name TEXT, url TEXT, last_token TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS sent_ads (token TEXT PRIMARY KEY)''')
conn.commit()

# بارگذاری فیلترها و آگهی‌های ارسال‌شده
def load_filters():
    c.execute("SELECT name, url, last_token FROM filters")
    return [{"name": row[0], "url": row[1], "last_token": row[2]} for row in c.fetchall()]

filters = load_filters()
sent_ads = {row[0] for row in c.execute("SELECT token FROM sent_ads").fetchall()}

# صفحه اصلی
@dp.message_handler(commands=['start', 'menu'])
async def start(message: types.Message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ اضافه کردن فیلتر", callback_data="add"),
        InlineKeyboardButton("📋 فیلترهای من", callback_data="list"),
        InlineKeyboardButton("🗑 حذف همه", callback_data="clear"),
        InlineKeyboardButton("ℹ️ راهنما", callback_data="help")
    )
    await message.answer(
        "🏠 <b>شکارچی شخصی دیوار</b>\n\n"
        "هر خونه جدیدی که با فیلترهات جور دربیاد، زیر ۳۰ ثانیه برات میاد!\n"
        f"فیلتر فعال: <b>{len(filters)}</b> تا",
        reply_markup=kb
    )

# اضافه کردن فیلتر جدید
@dp.callback_query_handler(text="add")
async def add_filter(call: types.CallbackQuery):
    await call.message.answer(
        "لینک جستجوی دیوار رو برام بفرست:\n\n"
        "مثال:\n"
        "https://divar.ir/s/tehran/buy-apartment?districts=1,2&price=5000000000-15000000000"
    )

# دریافت و ذخیره لینک
@dp.message_handler(content_types=['text'])
async def save_filter(message: types.Message):
    url = message.text.strip()
    if "divar.ir" not in url:
        await message.answer("❌ لینک معتبر دیوار نیست!")
        return

    # اسم فیلتر از لینک
    try:
        name = url.split("/")[-1].replace("-", " ").replace("?", "").title()
        if not name or len(name) < 3:
            name = f"فیلتر {len(filters)+1}"
    except:
        name = f"فیلتر {len(filters)+1}"

    c.execute("INSERT INTO filters (name, url) VALUES (?, ?)", (name, url))
    conn.commit()
    filters.append({"name": name, "url": url, "last_token": None})
    
    await message.answer(f"✅ فیلتر اضافه شد:\n<b>{name}</b>\nحالا هر آگهی جدیدی بیاد برات میفرستم!")

# نمایش فیلترها
@dp.callback_query_handler(text="list")
async def list_filters(call: types.CallbackQuery):
    if not filters:
        await call.message.answer("هنوز فیلتری نداری!")
        return
    text = "<b>فیلترهای فعال:</b>\n\n"
    for i, f in enumerate(filters, 1):
        text += f"{i}. {f['name']}\n"
    await call.message.answer(text)

# پاک کردن همه
@dp.callback_query_handler(text="clear")
async def clear_filters(call: types.CallbackQuery):
    c.execute("DELETE FROM filters")
    c.execute("DELETE FROM sent_ads")
    conn.commit()
    filters.clear()
    sent_ads.clear()
    await call.message.answer("🗑 همه چیز پاک شد!")

# راهنما
@dp.callback_query_handler(text="help")
async def help_cmd(call: types.CallbackQuery):
    await call.message.answer(
        "راهنما:\n\n"
        "1️⃣ برو دیوار → جستجو کن (منطقه، قیمت، متراژ و ...)\n"
        "2️⃣ لینک بالای مرورگر رو کپی کن\n"
        "3️⃣ اینجا بفرست\n"
        "4️⃣ تموم! هر آگهی جدید زیر ۳۰ ثانیه برات میاد!\n\n"
        "هر ۲۰ ثانیه یکبار چک می‌کنم 🔥"
    )

# تابع اصلی چک کردن آگهی‌ها
async def checker():
    while True:
        for filt in filters:
            try:
                async with aiohttp.ClientSession(timeout=20) as session:
                    async with session.get(filt["url"]) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text()

                # پیدا کردن توکن آگهی‌ها
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
                pass  # خطا رو نادیده بگیر تا ربات نیفته

        await asyncio.sleep(20)  # هر ۲۰ ثانیه چک کن

# ارسال آگهی کامل با آلبوم عکس
async def send_ad(token: str, filter_name: str):
    url = f"https://divar.ir/v/{token}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return
            html = await resp.text()

    # استخراج اطلاعات
    title = re.search(r'<h1[^>]*>(.*?)</h1>', html)
    title = title.group(1).strip() if title else "آگهی بدون عنوان"

    price = re.search(r'kt-unexpandable-row__value[^>]*>(.*?)</p>', html)
    price = price.group(1).strip() if price else "توافقی"

    desc = re.search(r'kt-description-row__text[^>]*>(.*?)</p>', html, re.S)
    desc = desc.group(1).strip().replace("<br>", "\n")[:300] + "..." if desc else ""

    phone = re.search(r'tel:(\d+)', html)
    phone_url = f"tel:{phone.group(1)}" if phone else None

    images = re.findall(r'[](https://s100.divar.ir/static/pictures/[^"]+)"', html)[:10]

    # متن
    caption = f"🏠 <b>آگهی جدید!</b>\n\n" \
              f"<b>{title}</b>\n" \
              f"💰 {price}\n" \
              f"📍 فیلتر: {filter_name}\n\n" \
              f"{desc}\n\n" \
              f"<a href='{url}'>مشاهده در دیوار</a>"

    # دکمه‌ها
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("باز کردن آگهی", url=url))
    if phone_url:
        kb.add(InlineKeyboardButton("تماس سریع ☎", url=phone_url))

    # ارسال آلبوم
    if images:
        media = [InputMediaPhoto(images[0], caption=caption, parse_mode="HTML")]
        for img in images[1:]:
            media.append(InputMediaPhoto(img))
        await bot.send_media_group(chat_id=TOKEN.split(":")[0], media=media)  # به خودت می‌فرسته
        await bot.send_message(chat_id=TOKEN.split(":")[0], text="دکمه‌ها:", reply_markup=kb)
    else:
        await bot.send_message(chat_id=TOKEN.split(":")[0], text=caption, reply_markup=kb, disable_web_page_preview=False)

# شروع ربات
if __name__ == "__main__":
    print("شکارچی شخصی دیوار شروع شد...")
    loop = asyncio.get_event_loop()
    loop.create_task(checker())
    executor.start_polling(dp, skip_updates=True)