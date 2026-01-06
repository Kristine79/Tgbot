"""
Модуль с клавиатурами для Telegram-бота
Все inline и reply клавиатуры для управления ботом
"""

from typing import List, Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, KeyboardBuilder

from config import PRODUCTS, SUPPORTED_CURRENCIES, config


# ============ Главное меню ============

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню с основными кнопками"""
    keyboard = [
        [KeyboardButton(text="🛒 Каталог")],
        [KeyboardButton(text="📋 Мои заказы"), KeyboardButton(text="💰 Баланс")],
        [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="👤 Профиль")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, input_field_placeholder="Выберите действие...")


def get_products_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора товаров"""
    builder = InlineKeyboardBuilder()
    
    for product_id, product in PRODUCTS.items():
        if product_id != 'custom':
            builder.button(
                text=f"{product['name']} - ${product['price_usd']}",
                callback_data=f"product:{product_id}"
            )
    
    builder.button(
        text="💎 Другой товар",
        callback_data="product:custom"
    )
    
    builder.adjust(1)
    return builder.as_markup()


# ============ Выбор валюты ============

def get_currencies_keyboard(product_id: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора криптовалюты"""
    builder = InlineKeyboardBuilder()
    
    for currency, networks in SUPPORTED_CURRENCIES.items():
        # Показываем первую доступную сеть
        display_networks = f" ({', '.join(networks[:2])})" if len(networks) > 1 else ""
        builder.button(
            text=f"💰 {currency}{display_networks}",
            callback_data=f"currency:{product_id}:{currency}"
        )
    
    builder.adjust(2)
    
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="back:products")
    )
    
    return builder.as_markup()


def get_networks_keyboard(product_id: str, currency: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора сети"""
    builder = InlineKeyboardBuilder()
    
    networks = SUPPORTED_CURRENCIES.get(currency, [])
    
    for network in networks:
        builder.button(
            text=f"⛓️ {network}",
            callback_data=f"network:{product_id}:{currency}:{network}"
        )
    
    builder.adjust(2)
    
    builder.row(
        InlineKeyboardButton(text="🔙 К выбору валюты", callback_data=f"back:currency:{product_id}")
    )
    
    return builder.as_markup()


# ============ Платёж ============

def payment_keyboard(invoice_id: str, order_id: str) -> InlineKeyboardMarkup:
    """Клавиатура для оплаты"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="💳 Оплатить",
        callback_data=f"pay:{order_id}"
    )
    
    builder.button(
        text="🔄 Проверить платёж",
        callback_data=f"check:{order_id}"
    )
    
    builder.button(
        text="❌ Отменить",
        callback_data=f"cancel:{order_id}"
    )
    
    builder.adjust(1)
    return builder.as_markup()


def payment_url_keyboard(pay_url: str, order_id: str) -> InlineKeyboardMarkup:
    """Клавиатура с ссылкой на оплату"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="🔗 Открыть CryptoBot",
        url=pay_url
    )
    
    builder.button(
        text="✅ Я оплатил",
        callback_data=f"check:{order_id}"
    )
    
    builder.button(
        text="❌ Отменить",
        callback_data=f"cancel:{order_id}"
    )
    
    builder.adjust(1)
    return builder.as_markup()


# ============ Заказы ============

def order_history_keyboard(orders: List[Dict[str, Any]], user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура истории заказов"""
    builder = InlineKeyboardBuilder()
    
    for order in orders:
        status_emoji = {
            'pending': '⏳',
            'paid': '✅',
            'failed': '❌',
            'cancelled': '🚫',
            'expired': '⏰'
        }.get(order['status'], '📦')
        
        builder.button(
            text=f"{status_emoji} #{order['order_id'][:8]} - ${order['amount_usd']:.2f}",
            callback_data=f"order_detail:{order['order_id']}"
        )
    
    builder.adjust(1)
    
    builder.row(
        InlineKeyboardButton(text="🔙 В меню", callback_data="back:menu")
    )
    
    return builder.as_markup()


def order_detail_keyboard(order: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Клавиатура деталей заказа"""
    builder = InlineKeyboardBuilder()
    
    if order['status'] == 'pending':
        builder.button(
            text="🔄 Проверить платёж",
            callback_data=f"check:{order['order_id']}"
        )
        
        builder.button(
            text="❌ Отменить",
            callback_data=f"cancel:{order['order_id']}"
        )
    
    elif order['status'] == 'paid':
        builder.button(
            text="📦 Статус заказа",
            callback_data=f"order_status:{order['order_id']}"
        )
    
    builder.row(
        InlineKeyboardButton(text="🔙 К заказам", callback_data="back:orders"),
        InlineKeyboardButton(text="🏠 В меню", callback_data="back:menu")
    )
    
    return builder.as_markup()


# ============ Админ панель ============

def admin_main_keyboard() -> ReplyKeyboardMarkup:
    """Главная клавиатура админа"""
    keyboard = [
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="📋 Все заказы"), KeyboardButton(text="⏳ Ожидающие")],
        [KeyboardButton(text="💰 Вывод"), KeyboardButton(text="🔄 Проверка")],
        [KeyboardButton(text="🧹 Очистка"), KeyboardButton(text="⚙️ Настройки")],
        [KeyboardButton(text="🔙 Обычное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def admin_orders_keyboard(page: int = 0, total_pages: int = 1) -> InlineKeyboardMarkup:
    """Клавиатура управления заказами"""
    builder = InlineKeyboardBuilder()
    
    # Навигация по страницам
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_orders:{page - 1}")
            )
        nav_buttons.append(
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="admin_page_info")
        )
        if page < total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton(text="▶️ Далее", callback_data=f"admin_orders:{page + 1}")
            )
        builder.row(*nav_buttons)
    
    builder.button(
        text="🔄 Обновить",
        callback_data="admin_orders:refresh"
    )
    
    builder.row(
        InlineKeyboardButton(text="🔙 В админку", callback_data="admin:menu")
    )
    
    return builder.as_markup()


def admin_order_detail_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """Клавиатура деталей заказа в админке"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="✅ Подтвердить вручную",
        callback_data=f"admin_confirm:{order_id}"
    )
    
    builder.button(
        text="❌ Отменить заказ",
        callback_data=f"admin_cancel:{order_id}"
    )
    
    builder.button(
        text="🔄 Проверить платёж",
        callback_data=f"admin_check:{order_id}"
    )
    
    builder.row(
        InlineKeyboardButton(text="🔙 К списку", callback_data="admin_orders:0"),
        InlineKeyboardButton(text="🏠 В меню", callback_data="admin:menu")
    )
    
    return builder.as_markup()


def admin_stats_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура статистики"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="📅 За сегодня",
        callback_data="stats:today"
    )
    
    builder.button(
        text="📅 За неделю",
        callback_data="stats:week"
    )
    
    builder.button(
        text="📅 За месяц",
        callback_data="stats:month"
    )
    
    builder.row(
        InlineKeyboardButton(text="🔙 В админку", callback_data="admin:menu")
    )
    
    return builder.as_markup()


def admin_check_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура принудительной проверки"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="🔄 Проверить все",
        callback_data="admin_check_all"
    )
    
    builder.button(
        text="🔙 В админку", callback_data="admin:menu"
    )
    
    return builder.as_markup()


def admin_cleanup_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура очистки"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="🧹 Удалить старые заказы",
        callback_data="admin_cleanup:old"
    )
    
    builder.button(
        text="📦 Очистить БД",
        callback_data="admin_cleanup:vacuum"
    )
    
    builder.row(
        InlineKeyboardButton(text="🔙 В админку", callback_data="admin:menu")
    )
    
    return builder.as_markup()


def admin_settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура настроек"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="🔔 Включить уведомления",
        callback_data="admin:notifications:on"
    )
    
    builder.button(
        text="🔕 Выключить уведомления",
        callback_data="admin:notifications:off"
    )
    
    builder.row(
        InlineKeyboardButton(text="🔙 В админку", callback_data="admin:menu")
    )
    
    return builder.as_markup()


# ============ Уведомления ============

def notification_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """Клавиатура для уведомлений"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="👁️ Просмотр",
        callback_data=f"view:{order_id}"
    )
    
    return builder.as_markup()


# ============ Служебные ============

def confirm_keyboard(action: str, item_id: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="✅ Да",
        callback_data=f"confirm:{action}:{item_id}"
    )
    
    builder.button(
        text="❌ Нет",
        callback_data=f"cancel:{action}:{item_id}"
    )
    
    return builder.as_markup()


def back_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой назад"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="🔙 Назад",
        callback_data=callback_data
    )
    
    return builder.as_markup()


def menu_keyboard() -> InlineKeyboardMarkup:
    """Простая клавиатура меню"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="🏠 Главное меню",
        callback_data="back:menu"
    )
    
    return builder.as_markup()


# ============ Генерация отчётов ============

def reports_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура отчётов"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="📊 Сводка",
        callback_data="report:summary"
    )
    
    builder.button(
        text="💰 По платежам",
        callback_data="report:payments"
    )
    
    builder.button(
        text="👥 По пользователям",
        callback_data="report:users"
    )
    
    builder.row(
        InlineKeyboardButton(text="🔙 В админку", callback_data="admin:menu")
    )
    
    return builder.as_markup()
