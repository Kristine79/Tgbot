"""
Telegram-бот для приёма криптовалютных платежей через CryptoBot
Основной файл приложения
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter, Text
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineQuery, InlineQueryResultArticle,
    InputTextMessageContent, BotCommand
)

from config import config, PRODUCTS, MESSAGES, SUPPORTED_CURRENCIES
from database import Database, Order
from cryptobot import CryptoBotAPI, create_payment, check_and_confirm_payment
from keyboards import (
    main_menu_keyboard, get_products_keyboard, get_currencies_keyboard,
    get_networks_keyboard, payment_keyboard, payment_url_keyboard,
    order_history_keyboard, order_detail_keyboard
)
from admin import AdminPanel, generate_daily_report, generate_weekly_report

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============ Состояния FSM ============

class PaymentStates(StatesGroup):
    """Состояния для процесса оплаты"""
    selecting_product = State()
    selecting_currency = State()
    selecting_network = State()
    creating_payment = State()
    payment_created = State()


# ============ Инициализация ============

# База данных
db = Database(config.database.db_path)

# API CryptoBot
cryptobot = CryptoBotAPI(
    api_token=config.cryptobot.api_token,
    app_id=config.cryptobot.app_id
)

# Бот и диспетчер
bot = Bot(token=config.bot.token, parse_mode='HTML')
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Админ-панель
admin_panel = AdminPanel(bot, db, cryptobot)


# ============ Команды ============

@router.message(Command('start'))
async def cmd_start(message: Message, state: FSMContext):
    """Обработка команды /start"""
    user = message.from_user
    
    # Создаём или получаем пользователя
    db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code
    )
    
    # Сбрасываем состояние
    await state.clear()
    
    # Отправляем приветствие
    await message.answer(
        MESSAGES['welcome'],
        reply_markup=main_menu_keyboard()
    )


@router.message(Command('menu'))
async def cmd_menu(message: Message, state: FSMContext):
    """Обработка команды /menu"""
    await state.clear()
    await message.answer(
        "🏠 <b>Главное меню</b>\n\nВыберите действие:",
        reply_markup=main_menu_keyboard()
    )


@router.message(Command('help'))
async def cmd_help(message: Message):
    """Обработка команды /help"""
    await message.answer(
        MESSAGES['help_text'].format(support=config.bot.support_username),
        reply_markup=main_menu_keyboard()
    )


@router.message(Command('history'))
async def cmd_history(message: Message):
    """Обработка команды /history"""
    user_id = message.from_user.id
    
    orders = db.get_user_orders(user_id)
    
    if not orders:
        await message.answer(
            "📋 <b>История заказов</b>\n\nУ вас пока нет заказов",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Форматируем заказы
    text = MESSAGES['order_history'].format(
        total_orders=len(orders),
        paid_orders=len([o for o in orders if o['status'] == 'paid']),
        pending_orders=len([o for o in orders if o['status'] == 'pending'])
    )
    
    await message.answer(
        text,
        reply_markup=order_history_keyboard(orders, user_id)
    )


# ============ Главное меню ============

@router.message(Text('🛒 Каталог'))
async def catalog(message: Message, state: FSMContext):
    """Показать каталог товаров"""
    await state.set_state(PaymentStates.selecting_product)
    
    await message.answer(
        "🛒 <b>Каталог товаров</b>\n\nВыберите товар:",
        reply_markup=get_products_keyboard()
    )


@router.message(Text('📋 Мои заказы'))
async def my_orders(message: Message):
    """Показать заказы пользователя"""
    user_id = message.from_user.id
    orders = db.get_user_orders(user_id)
    
    if not orders:
        await message.answer(
            "📋 <b>Мои заказы</b>\n\nУ вас пока нет заказов",
            reply_markup=main_menu_keyboard()
        )
        return
    
    text = MESSAGES['order_history'].format(
        total_orders=len(orders),
        paid_orders=len([o for o in orders if o['status'] == 'paid']),
        pending_orders=len([o for o in orders if o['status'] == 'pending'])
    )
    
    await message.answer(
        text,
        reply_markup=order_history_keyboard(orders, user_id)
    )


@router.message(Text('💰 Баланс'))
async def balance(message: Message):
    """Показать баланс пользователя"""
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    if user:
        text = f"""
💰 <b>Ваш баланс</b>

💵 Всего потрачено: ${user['total_spent']:.2f}
📦 Количество заказов: {user['orders_count']}

Спасибо за покупки! 🎁
        """
    else:
        text = "❌ Информация о балансе недоступна"
    
    await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(Text('👤 Профиль'))
async def profile(message: Message):
    """Показать профиль пользователя"""
    user = message.from_user
    
    text = f"""
👤 <b>Ваш профиль</b>

🆔 ID: {user.id}
📛 Имя: {user.first_name}
@{user.username if user.username else 'не указан'}
🌍 Язык: {user.language_code}

💡 Используйте /start для начала работы с ботом
    """
    
    await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(Text('❓ Помощь'))
async def help_cmd(message: Message):
    """Показать помощь"""
    await message.answer(
        MESSAGES['help_text'].format(support=config.bot.support_username),
        reply_markup=main_menu_keyboard()
    )


# ============ Выбор товара ============

@router.callback_query(PaymentStates.selecting_product, Text(startswith='product:'))
async def select_product(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора товара"""
    product_id = callback.data.split(':')[1]
    
    if product_id == 'custom':
        product_name = 'Индивидуальный заказ'
        price_usd = 0
    else:
        product = PRODUCTS.get(product_id)
        if not product:
            await callback.answer()
            return
        product_name = product['name']
        price_usd = product['price_usd']
    
    # Сохраняем данные
    await state.update_data(
        product_id=product_id,
        product_name=product_name,
        price_usd=price_usd
    )
    
    # Переходим к выбору валюты
    await state.set_state(PaymentStates.selecting_currency)
    
    text = MESSAGES['select_payment'].format(
        product_name=product_name,
        price=price_usd if price_usd > 0 else 'Уточняется'
    )
    
    await callback.message.edit_text(text, reply_markup=get_currencies_keyboard(product_id))
    await callback.answer()


# ============ Выбор валюты ============

@router.callback_query(PaymentStates.selecting_currency, Text(startswith='currency:'))
async def select_currency(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора валюты"""
    _, product_id, currency = callback.data.split(':')
    
    data = await state.get_data()
    
    # Если нужна сеть - показываем выбор сети
    networks = SUPPORTED_CURRENCIES.get(currency, [])
    
    if len(networks) > 1:
        await state.update_data(currency=currency)
        await state.set_state(PaymentStates.selecting_network)
        
        await callback.message.edit_text(
            f"💰 Валюта: <b>{currency}</b>\n\nВыберите сеть:",
            reply_markup=get_networks_keyboard(product_id, currency)
        )
    else:
        # Одна сеть - сразу создаём платёж
        network = networks[0] if networks else None
        await create_payment_callback(callback, state, currency, network)


# ============ Выбор сети ============

@router.callback_query(PaymentStates.selecting_network, Text(startswith='network:'))
async def select_network(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора сети"""
    _, product_id, currency, network = callback.data.split(':')
    
    await create_payment_callback(callback, state, currency, network)


# ============ Создание платежа ============

async def create_payment_callback(callback: CallbackQuery, state: FSMContext, 
                                  currency: str, network: str):
    """Создать платёж"""
    data = await state.get_data()
    product_id = data['product_id']
    product_name = data['product_name']
    price_usd = data['price_usd']
    
    await state.set_state(PaymentStates.creating_payment)
    
    # Генерируем ID заказа
    order_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    try:
        # Если цена не указана, запрашиваем у пользователя
        if price_usd <= 0:
            await state.set_state(PaymentStates.payment_created)
            await callback.message.edit_text(
                f"💰 <b>Индивидуальный заказ</b>\n\n"
                f"Товар: {product_name}\n\n"
                f"💵 Введите сумму в USD:",
                reply_markup=None
            )
            await callback.answer()
            return
        
        # Создаём счёт в CryptoBot
        invoice = await cryptobot.create_invoice(
            amount=price_usd,
            asset=currency,
            currency_type="crypto",
            description=f"Оплата заказа #{order_id}",
            expires_in=86400,
            payload=order_id
        )
        
        # Сохраняем заказ в БД
        order = Order(
            id=0,
            user_id=callback.from_user.id,
            product_id=product_id,
            product_name=product_name,
            amount_usd=price_usd,
            amount_crypto=float(invoice.amount),
            currency=invoice.asset or currency,
            network='',  # В новом API поле network не возвращается
            invoice_id=str(invoice.invoice_id),
            payment_url=invoice.bot_invoice_url or invoice.pay_url,
            status='pending',
            created_at=datetime.now().isoformat()
        )
        
        db.create_order(order)
        
        # Обновляем состояние
        await state.update_data(
            order_id=order_id,
            invoice_id=str(invoice.invoice_id),
            payment_url=invoice.pay_url
        )
        await state.set_state(PaymentStates.payment_created)
        
        # Показываем реквизиты для оплаты
        text = MESSAGES['payment_created'].format(
            order_id=order_id,
            product_name=product_name,
            amount=price_usd,
            payment_details=f"""
<b>{invoice.amount} {invoice.asset or currency}</b>
Ссылка для оплаты: {invoice.bot_invoice_url or invoice.pay_url}

💡 Оплатите по ссылке выше ⬆️""",
            network=invoice.asset or currency
        )
        
        await callback.message.edit_text(
            text,
            reply_markup=payment_url_keyboard(invoice.bot_invoice_url or invoice.pay_url, order_id)
        )
        
    except Exception as e:
        logger.error(f"Error creating payment: {e}")
        await callback.message.edit_text(
            "❌ <b>Ошибка создания платежа</b>\n\n"
            "Попробуйте позже или обратитесь в поддержку @{support}".format(
                support=config.bot.support_username
            )
        )
        await state.clear()
    
    await callback.answer()


@router.message(PaymentStates.payment_created, F.text.func(lambda x: x.replace('.', '').replace(',', '').isdigit()))
async def enter_amount(message: Message, state: FSMContext):
    """Ввод суммы для индивидуального заказа"""
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0")
            return
        
        data = await state.get_data()
        
        # Создаём платёж с указанной суммой
        order_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        invoice = await cryptobot.create_invoice(
            amount=amount,
            asset='USDT',
            currency_type="crypto",
            description=f"Оплата заказа #{order_id}",
            expires_in=86400,
            payload=order_id
        )
        
        # Сохраняем заказ
        order = Order(
            id=0,
            user_id=message.from_user.id,
            product_id=data['product_id'],
            product_name=data['product_name'],
            amount_usd=amount,
            amount_crypto=float(invoice.amount),
            currency=invoice.asset,
            network='',
            invoice_id=str(invoice.invoice_id),
            payment_url=invoice.bot_invoice_url or invoice.pay_url,
            status='pending',
            created_at=datetime.now().isoformat()
        )
        
        db.create_order(order)
        
        # Обновляем состояние
        await state.update_data(
            order_id=order_id,
            invoice_id=str(invoice.invoice_id),
            payment_url=invoice.bot_invoice_url or invoice.pay_url
        )
        
        # Показываем реквизиты
        text = MESSAGES['payment_created'].format(
            order_id=order_id,
            product_name=data['product_name'],
            amount=amount,
            payment_details=f"<b>{invoice.amount} USDT</b>\nСсылка: {invoice.bot_invoice_url or invoice.pay_url}",
            network='USDT'
        )
        
        await message.answer(
            text,
            reply_markup=payment_url_keyboard(invoice.bot_invoice_url or invoice.pay_url, order_id)
        )
        
    except Exception as e:
        logger.error(f"Error creating payment: {e}")
        await message.answer(
            "❌ Ошибка создания платежа. Попробуйте позже."
        )


# ============ Проверка платежа ============

@router.callback_query(Text(startswith='check:'))
async def check_payment(callback: CallbackQuery, state: FSMContext):
    """Проверить статус платежа"""
    order_id = callback.data.split(':')[1]
    
    order = db.get_order(order_id)
    
    if not order:
        await callback.answer("❌ Заказ не найден")
        return
    
    # Проверяем платёж (invoice_id теперь int в новом API)
    try:
        payment = await cryptobot.check_payment(int(order['invoice_id']))
        
        if payment.is_paid:
            # Обновляем заказ
            db.update_order_status(order_id, 'paid', datetime.now().isoformat())
            db.update_user_stats(order['user_id'], order['amount_usd'])
            
            # Создаём транзакцию
            if not db.transaction_exists(order['invoice_id']):
                db.create_transaction(
                    invoice_id=order['invoice_id'],
                    order_id=order_id,
                    amount=payment.amount,
                    currency=payment.asset,
                    network='',
                    status='paid'
                )
            
            # Показываем успех
            text = MESSAGES['payment_success'].format(
                order_id=order_id,
                amount=order['amount_usd'],
                date=datetime.now().strftime('%d.%m.%Y %H:%M')
            )
            
            await callback.message.edit_text(text, reply_markup=None)
            
            # Уведомляем админов
            for admin_id in config.bot.admin_ids:
                try:
                    await bot.send_message(
                        admin_id,
                        f"💰 <b>Новый платёж!</b>\n\n"
                        f"Заказ: #{order_id}\n"
                        f"Сумма: ${order['amount_usd']:.2f}\n"
                        f"Пользователь: {order['user_id']}"
                    )
                except Exception:
                    pass
            
        else:
            status_text = {
                'active': 'в процессе',
                'expired': 'истёк',
                'cancelled': 'отменён'
            }.get(payment.raw_response.get('status', ''), 'неизвестен')
            
            text = f"⏳ <b>Платёж {status_text}</b>\n\n{MESSAGES['payment_pending'].format(order_id=order_id)}"
            
            if callback.message:
                await callback.message.edit_text(text)
        
    except Exception as e:
        logger.error(f"Error checking payment: {e}")
        await callback.answer("❌ Ошибка проверки")
    
    await callback.answer()


# ============ Отмена платежа ============

@router.callback_query(Text(startswith='cancel:'))
async def cancel_payment(callback: CallbackQuery, state: FSMContext):
    """Отменить платёж"""
    order_id = callback.data.split(':')[1]
    
    order = db.get_order(order_id)
    
    if not order:
        await callback.answer("❌ Заказ не найден")
        return
    
    if order['status'] != 'pending':
        await callback.answer("Заказ уже обработан")
        return
    
    # Отменяем заказ
    db.update_order_status(order_id, 'cancelled')
    
    await callback.message.edit_text(
        f"🚫 <b>Заказ #{order_id} отменён</b>\n\n"
        "Хотите создать новый платёж?",
        reply_markup=None
    )
    
    await callback.answer()


# ============ Просмотр заказа ============

@router.callback_query(Text(startswith='order_detail:'))
async def view_order(callback: CallbackQuery):
    """Просмотр деталей заказа"""
    order_id = callback.data.split(':')[1]
    
    order = db.get_order(order_id)
    
    if not order:
        await callback.answer("❌ Заказ не найден")
        return
    
    # Проверяем, что это заказ пользователя
    if order['user_id'] != callback.from_user.id:
        await callback.answer("❌ Это не ваш заказ")
        return
    
    # Формируем текст
    status_emoji = {
        'pending': '⏳',
        'paid': '✅',
        'failed': '❌',
        'cancelled': '🚫',
        'expired': '⏰'
    }.get(order['status'], '📦')
    
    status_text = {
        'pending': 'Ожидает оплаты',
        'paid': 'Оплачен',
        'failed': 'Ошибка',
        'cancelled': 'Отменён',
        'expired': 'Истёк'
    }.get(order['status'], order['status'])
    
    text = f"""
📦 <b>Заказ #{order['order_id']}</b>

{status_emoji} Статус: {status_text}

📦 Товар: {order['product_name']}
💵 Сумма: ${order['amount_usd']:.2f}
💰 Оплачено: {order['amount_crypto']} {order['currency']}
⛓️ Сеть: {order['network']}

📅 Создан: {order['created_at']}
    """
    
    if order['paid_at']:
        text += f"\n✅ Оплачен: {order['paid_at']}"
    
    await callback.message.edit_text(
        text,
        reply_markup=order_detail_keyboard(order)
    )
    await callback.answer()


# ============ Навигация ============

@router.callback_query(Text(startswith='back:'))
async def navigate_back(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки Назад"""
    _, target = callback.data.split(':', 1)
    
    if target == 'products':
        await state.set_state(PaymentStates.selecting_product)
        await callback.message.edit_text(
            "🛒 <b>Каталог товаров</b>\n\nВыберите товар:",
            reply_markup=get_products_keyboard()
        )
    elif target == 'currency':
        await state.set_state(PaymentStates.selecting_currency)
        await callback.message.edit_text(
            "💰 <b>Выберите валюту</b>",
            reply_markup=get_products_keyboard()  # Здесь нужно сохранить product_id
        )
    elif target == 'menu':
        await state.clear()
        await callback.message.edit_text(
            "🏠 <b>Главное меню</b>",
            reply_markup=main_menu_keyboard()
        )
    elif target == 'orders':
        user_id = callback.from_user.id
        orders = db.get_user_orders(user_id)
        
        if orders:
            text = MESSAGES['order_history'].format(
                total_orders=len(orders),
                paid_orders=len([o for o in orders if o['status'] == 'paid']),
                pending_orders=len([o for o in orders if o['status'] == 'pending'])
            )
            
            await callback.message.edit_text(
                text,
                reply_markup=order_history_keyboard(orders, user_id)
            )
    
    await callback.answer()


# ============ Админ-команды ============

@router.message(Text('📊 Статистика'))
async def admin_stats(message: Message):
    """Показать статистику (админ)"""
    if message.from_user.id not in config.bot.admin_ids:
        return
    
    await admin_panel.show_stats(message)


@router.message(Text('📋 Все заказы'))
async def admin_all_orders(message: Message):
    """Показать все заказы (админ)"""
    if message.from_user.id not in config.bot.admin_ids:
        return
    
    await admin_panel.show_orders(message)


@router.message(Text('⏳ Ожидающие'))
async def admin_pending(message: Message):
    """Показать ожидающие заказы (админ)"""
    if message.from_user.id not in config.bot.admin_ids:
        return
    
    await admin_panel.show_pending_orders(message)


@router.message(Text('💰 Вывод'))
async def admin_balance(message: Message):
    """Показать баланс (админ)"""
    if message.from_user.id not in config.bot.admin_ids:
        return
    
    await admin_panel.show_balance(message)


@router.message(Text('🔄 Проверка'))
async def admin_check(message: Message):
    """Проверить все платежи (админ)"""
    if message.from_user.id not in config.bot.admin_ids:
        return
    
    await admin_panel.check_all_pending(message)


@router.message(Text('🧹 Очистка'))
async def admin_cleanup(message: Message):
    """Очистка БД (админ)"""
    if message.from_user.id not in config.bot.admin_ids:
        return
    
    await message.answer(
        "🧹 <b>Очистка базы данных</b>\n\nВыберите действие:",
        reply_markup=None  # Здесь нужна клавиатура очистки
    )


@router.message(Text('⚙️ Настройки'))
async def admin_settings(message: Message):
    """Настройки (админ)"""
    if message.from_user.id not in config.bot.admin_ids:
        return
    
    await message.answer(
        "⚙️ <b>Настройки</b>",
        reply_markup=None  # Здесь нужна клавиатура настроек
    )


@router.message(Text('🔙 Обычное меню'))
async def back_to_user_menu(message: Message):
    """Вернуться к обычному меню"""
    await message.answer(
        "🏠 <b>Главное меню</b>",
        reply_markup=main_menu_keyboard()
    )


# ============ Админ-колбэки ============

@router.callback_query(Text(startswith='admin:'))
async def admin_callback(callback: CallbackQuery):
    """Обработка админ-колбэков"""
    user_id = callback.from_user.id
    
    if user_id not in config.bot.admin_ids:
        await callback.answer("❌ Нет доступа")
        return
    
    _, action = callback.data.split(':', 1)
    
    if action == 'menu':
        await admin_panel.show_main_menu(callback.message)
    elif action.startswith('orders:'):
        page = int(action.split(':')[1])
        await admin_panel.show_orders(callback.message, page)
    elif action.startswith('order_detail:'):
        order_id = action.split(':', 1)[1]
        await admin_panel.show_order_detail(callback, order_id, is_callback=True)
    elif action.startswith('check:'):
        order_id = action.split(':', 1)[1]
        await admin_panel.manual_check_payment(callback, order_id, is_callback=True)
    elif action.startswith('confirm:'):
        order_id = action.split(':', 1)[1]
        await admin_panel.manual_confirm_order(callback, order_id)
    elif action.startswith('cancel:'):
        order_id = action.split(':', 1)[1]
        await admin_panel.manual_cancel_order(callback, order_id)
    elif action == 'refresh':
        await admin_panel.show_orders(callback.message)
    
    await callback.answer()


# ============ Inline-запросы ============

@router.inline_query()
async def inline_query(inline_query: InlineQuery):
    """Обработка inline-запросов"""
    results = [
        InlineQueryResultArticle(
            id='1',
            title='💰 CryptoPay Bot',
            input_message_content=InputTextMessageContent(
                message_text='💰 Используйте @CryptoPayBot для оплаты',
                parse_mode='HTML'
            ),
            description='Бот для приёма криптовалютных платежей'
        )
    ]
    
    await bot.answer_inline_query(inline_query.id, results)


# ============ Запуск бота ============

async def main():
    """Основная функция запуска"""
    # Устанавливаем команды бота
    await bot.set_my_commands([
        BotCommand(command='start', description='Запустить бота'),
        BotCommand(command='menu', description='Главное меню'),
        BotCommand(command='help', description='Помощь'),
        BotCommand(command='history', description='История заказов')
    ])
    
    # Запускаем polling
    logger.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
    finally:
        # Закрываем соединения
        import asyncio
        asyncio.run(cryptobot.close())
