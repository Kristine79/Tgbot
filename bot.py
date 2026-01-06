# ===========================================
# ПРОСТОЙ TELEGRAM БОТ ДЛЯ КРИПТОВАЛЮТНЫХ ПЛАТЕЖЕЙ
# CryptoBot API
# ===========================================
# Автор: MiniMax Agent
# Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api
# ===========================================

import os
import sqlite3
import asyncio
import logging
import uuid
import hashlib
import hmac
import json
from datetime import datetime
from threading import Thread
from flask import Flask, request, jsonify
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

# aiogram 3.x - библиотека для Telegram
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, Text
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, KeyboardButton, ReplyKeyboardMarkup,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ===========================================
# КОНФИГУРАЦИЯ (только эти настройки нужно изменить)
# ===========================================

# Загружаем переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN", "")  # Токен бота от @BotFather
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]  # ID админов
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "")  # username поддержки без @

# CryptoBot настройки
CRYPTOBOT_API_TOKEN = os.getenv("CRYPTOBOT_API_TOKEN", "")  # API токен от @CryptoBot
CRYPTOBOT_APP_ID = os.getenv("CRYPTOBOT_APP_ID", "")  # ID приложения (опционально)

# База данных
DB_PATH = os.getenv("DB_PATH", "payments.db")

# Вебхук
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
LISTEN_PORT = int(os.getenv("PORT", "8080"))
LISTEN_HOST = os.getenv("LISTEN_HOST", "0.0.0.0")

# ===========================================
# НАСТРОЙКИ БОТА
# ===========================================

# Поддерживаемые криптовалюты
ASSETS = ["USDT", "BTC", "ETH", "TON", "TRX", "USDC", "LTC", "BNB"]

# Товары (название -> цена в USD)
PRODUCTS = {
    "basic": {"name": "Базовый тариф", "price": 9.99},
    "standard": {"name": "Стандартный тариф", "price": 29.99},
    "premium": {"name": "Премиум тариф", "price": 99.99},
}

# ===========================================
# ЛОГИРОВАНИЕ
# ===========================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===========================================
# БАЗА ДАННЫХ
# ===========================================

def init_db():
    """Создать таблицы в базе данных"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            total_spent REAL DEFAULT 0,
            orders_count INTEGER DEFAULT 0
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE,
            user_id INTEGER,
            product_id TEXT,
            product_name TEXT,
            amount_usd REAL,
            asset TEXT,
            invoice_id INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            paid_at TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER,
            order_id TEXT,
            amount REAL,
            asset TEXT,
            status TEXT,
            created_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")

def get_db_connection():
    """Получить соединение с БД"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ===========================================
# CRYPTOBOT API (упрощённый)
# ===========================================

class CryptoBotAPI:
    """Простой клиент для CryptoBot API"""
    
    BASE_URL = "https://pay.crypt.bot/api"
    
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            'Crypto-Pay-API-Token': token,
            'Content-Type': 'application/json'
        }
    
    async def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Сделать запрос к API"""
        import aiohttp
        
        url = f"{self.BASE_URL}/{endpoint}"
        
        async with aiohttp.ClientSession() as session:
            if method == "GET":
                async with session.get(url, headers=self.headers, params=data) as resp:
                    return await resp.json()
            else:
                async with session.post(url, json=data, headers=self.headers) as resp:
                    return await resp.json()
    
    async def create_invoice(
        self,
        amount: float,
        asset: str,
        description: str = "Payment",
        expires_in: int = 86400,
        payload: str = None
    ) -> dict:
        """Создать счёт на оплату"""
        data = {
            "amount": str(amount),
            "asset": asset,
            "currency_type": "crypto",
            "description": description[:1024],
            "expires_in": expires_in
        }
        
        if payload:
            data["payload"] = payload
        
        result = await self._request("POST", "createInvoice", data)
        
        if result.get("ok"):
            return result["result"]
        else:
            error = result.get("error", {}).get("message", "Unknown error")
            raise Exception(f"CryptoBot error: {error}")
    
    async def get_invoice(self, invoice_id: int) -> Optional[dict]:
        """Получить информацию о счёте"""
        result = await self._request("GET", f"getInvoice/{invoice_id}")
        
        if result.get("ok"):
            return result["result"]
        return None
    
    async def check_payment(self, invoice_id: int) -> dict:
        """Проверить статус платежа"""
        invoice = await self.get_invoice(invoice_id)
        
        if invoice is None:
            return {"status": "unknown", "is_paid": False}
        
        status_map = {
            "active": "pending",
            "paid": "paid",
            "expired": "expired"
        }
        
        status = status_map.get(invoice.get("status", ""), "unknown")
        
        return {
            "status": status,
            "is_paid": status == "paid",
            "amount": invoice.get("amount", "0"),
            "asset": invoice.get("asset", ""),
            "paid_usd_rate": invoice.get("paid_usd_rate", "")
        }
    
    async def get_balance(self) -> list:
        """Получить баланс"""
        result = await self._request("GET", "getBalance")
        
        if result.get("ok"):
            return result.get("balance", [])
        return []
    
    async def get_me(self) -> dict:
        """Информация о приложении"""
        result = await self._request("GET", "getMe")
        
        if result.get("ok"):
            return result["result"]
        return {}

# ===========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ===========================================

def verify_webhook_signature(token: str, body: bytes, signature: str) -> bool:
    """Проверить подпись вебхука"""
    if not signature or not body:
        return False
    
    secret = hashlib.sha256(token.encode()).digest()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    
    return hmac.compare_digest(signature, expected)

def format_order_text(order: dict) -> str:
    """Форматировать текст заказа"""
    status_emoji = {
        "pending": "⏳",
        "paid": "✅",
        "expired": "⏰",
        "cancelled": "🚫"
    }
    
    emoji = status_emoji.get(order["status"], "📦")
    status_text = {
        "pending": "Ожидает оплаты",
        "paid": "Оплачен",
        "expired": "Истёк",
        "cancelled": "Отменён"
    }
    
    return f"""
{emoji} <b>Заказ #{order["order_id"][:12]}</b>

📦 Товар: {order["product_name"]}
💰 Сумма: ${order["amount_usd"]:.2f}
💳 Криптовалюта: {order["asset"]}
📅 Создан: {order["created_at"][:16]}

📍 Статус: {status_text.get(order["status"], order["status"])}
    """.strip()

# ===========================================
# КЛАВИАТУРЫ
# ===========================================

def main_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Каталог")],
            [KeyboardButton(text="📋 Мои заказы")],
            [KeyboardButton(text="❓ Помощь")]
        ],
        resize_keyboard=True
    )

def catalog_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура каталога"""
    keyboard = []
    
    for product_id, product in PRODUCTS.items():
        keyboard.append([
            InlineKeyboardButton(
                text=f"{product['name']} - ${product['price']}",
                callback_data=f"product:{product_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def assets_keyboard(product_id: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора криптовалюты"""
    keyboard = []
    
    for asset in ASSETS:
        keyboard.append([
            InlineKeyboardButton(
                text=f"💰 {asset}",
                callback_data=f"asset:{product_id}:{asset}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back:catalog")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def payment_keyboard(pay_url: str, order_id: str) -> InlineKeyboardMarkup:
    """Клавиатура оплаты"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=pay_url)],
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check:{order_id}")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel:{order_id}")]
        ]
    )

def order_detail_keyboard(order_id: str, status: str) -> InlineKeyboardMarkup:
    """Клавиатура деталей заказа"""
    keyboard = []
    
    if status == "pending":
        keyboard.append([
            InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check:{order_id}"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel:{order_id}")
        ])
    
    keyboard.append([InlineKeyboardButton(text="🔙 К заказам", callback_data="back:orders")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def admin_keyboard() -> ReplyKeyboardMarkup:
    """Админ-клавиатура"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📋 Заказы"), KeyboardButton(text="💰 Баланс")],
            [KeyboardButton(text="🔄 Проверить платежи")],
            [KeyboardButton(text="🔙 Обычное меню")]
        ],
        resize_keyboard=True
    )

# ===========================================
# СОСТОЯНИЯ FSM
# ===========================================

class PaymentState(StatesGroup):
    """Состояния для оплаты"""
    waiting_for_amount = State()

# ===========================================
# ИНИЦИАЛИЗАЦИЯ
# ===========================================

# База данных
init_db()

# CryptoBot API
cryptobot = CryptoBotAPI(CRYPTOBOT_API_TOKEN)

# Бот и диспетчер
bot = Bot(token=BOT_TOKEN, parse_mode='HTML')
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# ===========================================
# КОМАНДЫ БОТА
# ===========================================

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Команда /start"""
    user = message.from_user
    
    # Сохраняем пользователя в БД
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO users (user_id, username, first_name)
        VALUES (?, ?, ?)
    """, (user.id, user.username, user.first_name))
    conn.commit()
    conn.close()
    
    await state.clear()
    
    await message.answer(
        f"""
👋 <b>Добро пожаловать, {user.first_name}!</b>

💰 Это бот для приёма криптовалютных платежей.

🛒 Используйте кнопку <b>Каталог</b> для просмотра товаров.

❓ Нужна помощь? @{SUPPORT_USERNAME}
        """.strip(),
        reply_markup=main_keyboard()
    )

@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    """Команда /menu"""
    await state.clear()
    await message.answer("🏠 <b>Главное меню</b>", reply_markup=main_keyboard())

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Команда /help"""
    await message.answer(
        f"""
❓ <b>Помощь</b>

🛒 <b>Каталог</b> - выбрать товар
📋 <b>Мои заказы</b> - история покупок

💳 Оплата происходит через @CryptoBot

📞 Поддержка: @{SUPPORT_USERNAME}
        """,
        reply_markup=main_keyboard()
    )

@router.message(Text("❓ Помощь"))
async def help_button(message: Message):
    """Кнопка помощи"""
    await cmd_help(message)

# ===========================================
# КАТАЛОГ
# ===========================================

@router.message(Text("🛒 Каталог"))
async def catalog(message: Message, state: FSMContext):
    """Показать каталог"""
    await state.set_state(PaymentState.waiting_for_amount)
    
    text = "🛒 <b>Каталог товаров</b>\n\nВыберите товар:"
    
    await message.answer(text, reply_markup=catalog_keyboard())

@router.callback_query(Text(startswith="product:"))
async def select_product(callback: CallbackQuery, state: FSMContext):
    """Выбор товара"""
    product_id = callback.data.split(":")[1]
    product = PRODUCTS.get(product_id)
    
    if not product:
        await callback.answer("Товар не найден")
        return
    
    await state.update_data(product_id=product_id, product_name=product["name"], price=product["price"])
    
    text = f"📦 <b>{product['name']}</b>\n\n💰 Цена: ${product['price']}\n\nВыберите криптовалюту для оплаты:"
    
    await callback.message.edit_text(text, reply_markup=assets_keyboard(product_id))
    await callback.answer()

@router.callback_query(Text(startswith="asset:"))
async def select_asset(callback: CallbackQuery, state: FSMContext):
    """Выбор криптовалюты и создание счёта"""
    _, product_id, asset = callback.data.split(":")
    data = await state.get_data()
    
    product_name = data.get("product_name", "Товар")
    price_usd = data.get("price", 0)
    
    # Генерируем ID заказа
    order_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    try:
        # Создаём счёт в CryptoBot
        invoice = await cryptobot.create_invoice(
            amount=price_usd,
            asset=asset,
            description=f"Оплата заказа #{order_id}",
            expires_in=86400,
            payload=order_id
        )
        
        # Сохраняем заказ в БД
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO orders (order_id, user_id, product_id, product_name, amount_usd, asset, invoice_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_id, callback.from_user.id, product_id, product_name,
            price_usd, asset, invoice["invoice_id"], "pending", datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        # Сохраняем в состоянии
        await state.update_data(
            order_id=order_id,
            invoice_id=invoice["invoice_id"],
            payment_url=invoice.get("bot_invoice_url", invoice.get("pay_url", ""))
        )
        
        # Отправляем пользователю информацию об оплате
        pay_url = invoice.get("bot_invoice_url", invoice.get("pay_url", ""))
        
        text = f"""
✅ <b>Счёт создан!</b>

📦 Заказ: {product_name}
💰 Сумма: ${price_usd}
💳 Оплата: {invoice['amount']} {asset}

🔗 <a href="{pay_url}">Оплатить в CryptoBot</a>

⚠️ После оплаты нажмите "Я оплатил"
        """.strip()
        
        await callback.message.edit_text(
            text,
            reply_markup=payment_keyboard(pay_url, order_id),
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Ошибка создания счёта: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка создания счёта: {e}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 В каталог", callback_data="back:catalog")]]
            )
        )
    
    await callback.answer()

# ===========================================
# ПРОВЕРКА И ОТМЕНА ПЛАТЕЖА
# ===========================================

@router.callback_query(Text(startswith="check:"))
async def check_payment(callback: CallbackQuery):
    """Проверить статус платежа"""
    order_id = callback.data.split(":")[1]
    
    # Получаем заказ из БД
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    order = cursor.fetchone()
    
    if not order:
        await callback.answer("❌ Заказ не найден")
        return
    
    invoice_id = order["invoice_id"]
    
    try:
        # Проверяем платёж в CryptoBot
        payment = await cryptobot.check_payment(int(invoice_id))
        
        if payment["is_paid"]:
            # Обновляем статус
            cursor.execute("""
                UPDATE orders SET status = 'paid', paid_at = ? WHERE order_id = ?
            """, (datetime.now().isoformat(), order_id))
            
            # Обновляем статистику пользователя
            cursor.execute("""
                UPDATE users SET total_spent = total_spent + ?, orders_count = orders_count + 1
                WHERE user_id = ?
            """, (order["amount_usd"], order["user_id"]))
            
            # Создаём транзакцию
            cursor.execute("""
                INSERT INTO transactions (invoice_id, order_id, amount, asset, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (invoice_id, order_id, payment["amount"], payment["asset"], "paid", datetime.now().isoformat()))
            
            conn.commit()
            
            text = f"""
🎉 <b>Платёж получен!</b>

✅ Заказ #{order_id[:12]} оплачен
💰 Сумма: ${order["amount_usd"]}
💳 Криптовалюта: {payment['amount']} {payment['asset']}

📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}

Спасибо за покупку! 🎁
            """.strip()
            
            await callback.message.edit_text(text)
            
            # Уведомляем админов
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(
                        admin_id,
                        f"💰 <b>Новый платёж!</b>\n\n"
                        f"Заказ: #{order_id[:12]}\n"
                        f"Сумма: ${order['amount_usd']}\n"
                        f"Пользователь: {order['user_id']}"
                    )
                except:
                    pass
        
        else:
            status_text = {
                "pending": "в процессе",
                "expired": "истёк"
            }.get(payment["status"], "неизвестен")
            
            text = f"""
⏳ <b>Платёж {status_text}</b>

📦 Заказ: #{order_id[:12]}
💰 Сумма: ${order["amount_usd"]}

💡 Платёж может занять несколько минут.
Попробуйте проверить позже.
            """.strip()
            
            await callback.message.edit_text(text, reply_markup=payment_keyboard("", order_id))
    
    except Exception as e:
        logger.error(f"Ошибка проверки платежа: {e}")
        await callback.answer("❌ Ошибка проверки")
    
    conn.close()
    await callback.answer()

@router.callback_query(Text(startswith="cancel:"))
async def cancel_order(callback: CallbackQuery):
    """Отменить заказ"""
    order_id = callback.data.split(":")[1]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,))
    order = cursor.fetchone()
    
    if not order:
        await callback.answer("Заказ не найден")
        return
    
    if order["status"] != "pending":
        await callback.answer("Заказ уже обработан")
        return
    
    cursor.execute("UPDATE orders SET status = 'cancelled' WHERE order_id = ?", (order_id,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(
        f"🚫 <b>Заказ #{order_id[:12]} отменён</b>",
        reply_markup=None
    )
    
    await callback.answer()

# ===========================================
# ИСТОРИЯ ЗАКАЗОВ
# ===========================================

@router.message(Text("📋 Мои заказы"))
async def my_orders(message: Message):
    """Показать историю заказов"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 20
    """, (message.from_user.id,))
    
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        await message.answer(
            "📋 <b>Мои заказы</b>\n\nУ вас пока нет заказов",
            reply_markup=main_keyboard()
        )
        return
    
    text = f"📋 <b>Мои заказы</b> ({len(orders)})\n\n"
    
    for order in orders[:10]:
        status_emoji = {"pending": "⏳", "paid": "✅", "expired": "⏰", "cancelled": "🚫"}
        emoji = status_emoji.get(order["status"], "📦")
        
        text += f"{emoji} #{order['order_id'][:10]} - ${order['amount_usd']:.2f} ({order['asset']})\n"
    
    # Создаём клавиатуру с заказами
    keyboard = []
    for order in orders[:5]:
        status_emoji = {"pending": "⏳", "paid": "✅", "expired": "⏰", "cancelled": "🚫"}
        keyboard.append([
            InlineKeyboardButton(
                text=f"{status_emoji.get(order['status'], '📦')} #{order['order_id'][:10]} - ${order['amount_usd']:.2f}",
                callback_data=f"order:{order['order_id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back:menu")])
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.callback_query(Text(startswith="order:"))
async def order_detail(callback: CallbackQuery):
    """Детали заказа"""
    order_id = callback.data.split(":")[1]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    order = cursor.fetchone()
    conn.close()
    
    if not order:
        await callback.answer("Заказ не найден")
        return
    
    text = format_order_text(dict(order))
    
    await callback.message.edit_text(
        text,
        reply_markup=order_detail_keyboard(order_id, order["status"])
    )
    
    await callback.answer()

@router.callback_query(Text("back:catalog"))
async def back_to_catalog(callback: CallbackQuery, state: FSMContext):
    """Назад в каталог"""
    await state.set_state(PaymentState.waiting_for_amount)
    
    await callback.message.edit_text(
        "🛒 <b>Каталог товаров</b>\n\nВыберите товар:",
        reply_markup=catalog_keyboard()
    )
    
    await callback.answer()

@router.callback_query(Text("back:menu"))
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    """Назад в меню"""
    await state.clear()
    
    await callback.message.edit_text("🏠 <b>Главное меню</b>", reply_markup=main_keyboard())
    
    await callback.answer()

@router.callback_query(Text("back:orders"))
async def back_to_orders(callback: CallbackQuery):
    """Назад к заказам"""
    await callback.message.delete()
    
    # Вызываем функцию просмотра заказов
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 20", (callback.from_user.id,))
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        await callback.message.answer(
            "📋 <b>Мои заказы</b>\n\nУ вас пока нет заказов",
            reply_markup=main_keyboard()
        )
        return
    
    text = f"📋 <b>Мои заказы</b> ({len(orders)})\n\n"
    
    for order in orders[:10]:
        status_emoji = {"pending": "⏳", "paid": "✅", "expired": "⏰", "cancelled": "🚫"}
        emoji = status_emoji.get(order["status"], "📦")
        text += f"{emoji} #{order['order_id'][:10]} - ${order['amount_usd']:.2f} ({order['asset']})\n"
    
    keyboard = []
    for order in orders[:5]:
        status_emoji = {"pending": "⏳", "paid": "✅", "expired": "⏰", "cancelled": "🚫"}
        keyboard.append([
            InlineKeyboardButton(
                text=f"{status_emoji.get(order['status'], '📦')} #{order['order_id'][:10]} - ${order['amount_usd']:.2f}",
                callback_data=f"order:{order['order_id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back:menu")])
    
    await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    
    await callback.answer()

# ===========================================
# АДМИН-ПАНЕЛЬ
# ===========================================

@router.message(Text("📊 Статистика"))
async def admin_stats(message: Message):
    """Статистика для админа"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Общая статистика
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount_usd), 0) FROM orders WHERE status = 'paid'")
    total_paid = cursor.fetchone()
    
    # За сегодня
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(amount_usd), 0) FROM orders
        WHERE status = 'paid' AND created_at LIKE ?
    """, (f"{today}%",))
    today_stats = cursor.fetchone()
    
    # Всего заказов
    cursor.execute("SELECT COUNT(*) FROM orders")
    total_orders = cursor.fetchone()[0]
    
    # Пользователи
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    conn.close()
    
    text = f"""
📊 <b>Статистика</b>

💰 <b>За сегодня:</b>
• Заказов: {today_stats[0]}
• Получено: ${today_stats[1]:.2f}

📈 <b>Всего:</b>
• Всего заказов: {total_orders}
• Оплачено: {total_paid[0]} (${total_paid[1]:.2f})
• Пользователей: {total_users}
    """.strip()
    
    await message.answer(text, reply_markup=admin_keyboard())

@router.message(Text("📋 Заказы"))
async def admin_orders(message: Message):
    """Все заказы для админа"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 10")
    orders = cursor.fetchall()
    conn.close()
    
    if not orders:
        await message.answer("📋 Заказов пока нет", reply_markup=admin_keyboard())
        return
    
    text = "📋 <b>Последние заказы</b>\n\n"
    
    for order in orders:
        status_emoji = {"pending": "⏳", "paid": "✅", "expired": "⏰", "cancelled": "🚫"}
        emoji = status_emoji.get(order["status"], "📦")
        
        text += f"{emoji} #{order['order_id'][:12]} - ${order['amount_usd']:.2f} ({order['user_id']})\n"
    
    await message.answer(text, reply_markup=admin_keyboard())

@router.message(Text("💰 Баланс"))
async def admin_balance(message: Message):
    """Баланс приложения"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        balance = await cryptobot.get_balance()
        
        if balance:
            text = "💰 <b>Баланс приложения</b>\n\n"
            
            for asset in balance:
                text += f"• {asset['currency_code']}: {asset['available']}\n"
            
            await message.answer(text, reply_markup=admin_keyboard())
        else:
            await message.answer("❌ Не удалось получить баланс", reply_markup=admin_keyboard())
    
    except Exception as e:
        logger.error(f"Ошибка получения баланса: {e}")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=admin_keyboard())

@router.message(Text("🔄 Проверить платежи"))
async def admin_check_all(message: Message):
    """Проверить все ожидающие платежи"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM orders WHERE status = 'pending'")
    pending_orders = cursor.fetchall()
    
    if not pending_orders:
        await message.answer("✅ Нет ожидающих платежей", reply_markup=admin_keyboard())
        conn.close()
        return
    
    checked = 0
    confirmed = 0
    
    for order in pending_orders:
        try:
            payment = await cryptobot.check_payment(int(order["invoice_id"]))
            
            if payment["is_paid"]:
                cursor.execute("""
                    UPDATE orders SET status = 'paid', paid_at = ? WHERE id = ?
                """, (datetime.now().isoformat(), order["id"]))
                
                cursor.execute("""
                    UPDATE users SET total_spent = total_spent + ?, orders_count = orders_count + 1
                    WHERE user_id = ?
                """, (order["amount_usd"], order["user_id"]))
                
                confirmed += 1
                
                # Уведомляем пользователя
                try:
                    await bot.send_message(
                        order["user_id"],
                        f"🎉 <b>Платёж получен!</b>\n\n"
                        f"Заказ #{order['order_id'][:12]} оплачен!\n"
                        f"Сумма: ${order['amount_usd']}"
                    )
                except:
                    pass
            
            checked += 1
            
            await asyncio.sleep(0.5)  # Небольшая задержка
        
        except Exception as e:
            logger.error(f"Ошибка проверки заказа {order['order_id']}: {e}")
    
    conn.commit()
    conn.close()
    
    await message.answer(
        f"🔄 <b>Проверка завершена</b>\n\n"
        f"Проверено: {checked}\n"
        f"Подтверждено: {confirmed}",
        reply_markup=admin_keyboard()
    )

@router.message(Text("🔙 Обычное меню"))
async def back_to_user_menu(message: Message, state: FSMContext):
    """Вернуться к обычному меню"""
    await state.clear()
    await message.answer("🏠 <b>Главное меню</b>", reply_markup=main_keyboard())

# ===========================================
# ВЕБХУК (Flask)
# ===========================================

app = Flask(__name__)

@app.route("/")
def index():
    """Главная страница"""
    return "CryptoPay Bot Webhook Server"

@app.route("/health")
def health():
    """Проверка состояния"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    """Обработка вебхуков от CryptoBot"""
    try:
        body = request.get_data()
        signature = request.headers.get("crypto-pay-api-signature", "")
        
        # Проверяем подпись
        if signature and WEBHOOK_SECRET:
            if not verify_webhook_signature(CRYPTOBOT_API_TOKEN, body, signature):
                logger.warning("Неверная подпись вебхука")
                # В продакшене вернуть 401
        
        payload = json.loads(body)
        
        # Проверяем тип обновления
        if payload.get("update_type") == "invoice_paid":
            invoice_data = payload.get("payload", {})
            invoice_id = invoice_data.get("invoice_id")
            order_id = invoice_data.get("payload", "")
            
            logger.info(f"Вебхук: invoice_paid, invoice_id={invoice_id}")
            
            if order_id:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
                order = cursor.fetchone()
                
                if order and order["status"] == "pending":
                    # Обновляем заказ
                    cursor.execute("""
                        UPDATE orders SET status = 'paid', paid_at = ? WHERE order_id = ?
                    """, (datetime.now().isoformat(), order_id))
                    
                    cursor.execute("""
                        UPDATE users SET total_spent = total_spent + ?, orders_count = orders_count + 1
                        WHERE user_id = ?
                    """, (order["amount_usd"], order["user_id"]))
                    
                    cursor.execute("""
                        INSERT INTO transactions (invoice_id, order_id, amount, asset, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        invoice_id, order_id,
                        invoice_data.get("amount", "0"),
                        invoice_data.get("asset", ""),
                        "paid", datetime.now().isoformat()
                    ))
                    
                    conn.commit()
                    conn.close()
                    
                    # Уведомляем пользователя
                    try:
                        bot.send_message(
                            order["user_id"],
                            f"🎉 <b>Платёж получен!</b>\n\n"
                            f"Заказ #{order_id[:12]} оплачен!\n"
                            f"Сумма: ${order['amount_usd']}"
                        )
                    except:
                        pass
                    
                    logger.info(f"Заказ {order_id} оплачен через вебхук")
        
        return jsonify({"status": "ok"})
    
    except Exception as e:
        logger.error(f"Ошибка вебхука: {e}")
        return jsonify({"error": str(e)}), 500

def run_flask():
    """Запуск Flask в отдельном потоке"""
    app.run(host=LISTEN_HOST, port=LISTEN_PORT, debug=False, threaded=True)

# ===========================================
# ЗАПУСК
# ===========================================

async def main():
    """Основная функция запуска"""
    logger.info("=" * 50)
    logger.info("🚀 Запуск CryptoPay Bot")
    logger.info("=" * 50)
    
    # Проверяем токены
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не установлен!")
        logger.info("Установите переменную окружения BOT_TOKEN")
        return
    
    if not CRYPTOBOT_API_TOKEN:
        logger.error("❌ CRYPTOBOT_API_TOKEN не установлен!")
        logger.info("Установите переменную окружения CRYPTOBOT_API_TOKEN")
        return
    
    # Проверяем подключение к CryptoBot
    try:
        app_info = await cryptobot.get_me()
        logger.info(f"✅ CryptoBot подключён: {app_info.get('name', 'Unknown')}")
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к CryptoBot: {e}")
        return
    
    # Запускаем Flask в фоновом режиме
    if WEBHOOK_HOST and WEBHOOK_PATH:
        Thread(target=run_flask, daemon=True).start()
        logger.info(f"🌐 Вебхук сервер запущен на порту {LISTEN_PORT}")
    
    # Запускаем polling
    logger.info("🤖 Бот запущен и ожидает сообщений...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
