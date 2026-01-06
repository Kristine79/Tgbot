"""
Модуль административных функций
Статистика, управление заказами, отчёты
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from aiogram import Bot
from aiogram.types import Message, CallbackQuery

from database import Database, Order
from cryptobot import CryptoBotAPI, check_and_confirm_payment
from keyboards import (
    admin_main_keyboard, admin_orders_keyboard, 
    admin_order_detail_keyboard, admin_stats_keyboard,
    admin_check_keyboard, admin_cleanup_keyboard,
    admin_settings_keyboard, reports_keyboard
)
from config import config, MESSAGES


class AdminPanel:
    """Класс административной панели"""
    
    def __init__(self, bot: Bot, db: Database, cryptobot: CryptoBotAPI):
        self.bot = bot
        self.db = db
        self.cryptobot = cryptobot
        self.notifications_enabled = True
    
    async def show_main_menu(self, message: Message):
        """Показать главное меню админки"""
        user_id = message.from_user.id
        
        if user_id not in config.bot.admin_ids:
            await message.answer("❌ У вас нет доступа к админ-панели")
            return
        
        await message.answer(
            "⚙️ <b>Панель администратора</b>\n\n"
            "Выберите действие из меню:",
            reply_markup=admin_main_keyboard()
        )
    
    async def show_stats(self, message: Message, period: str = 'all'):
        """Показать статистику"""
        user_id = message.from_user.id
        
        if user_id not in config.bot.admin_ids:
            return
        
        stats = self.db.get_stats()
        
        # Форматируем статистику
        today_orders = stats.get('today_orders', 0) or 0
        today_amount = stats.get('today_amount', 0) or 0
        total_orders = stats.get('total_orders', 0) or 0
        total_amount = stats.get('total_amount', 0) or 0
        successful_payments = stats.get('successful_payments', 0) or 0
        
        # Получаем дополнительную статистику
        if period == 'today':
            period_stats = self._get_period_stats('today')
            title = "📊 <b>Статистика за сегодня</b>"
        elif period == 'week':
            period_stats = self._get_period_stats('week')
            title = "📊 <b>Статистика за неделю</b>"
        elif period == 'month':
            period_stats = self._get_period_stats('month')
            title = "📊 <b>Статистика за месяц</b>"
        else:
            period_stats = {
                'orders': total_orders,
                'amount': total_amount,
                'successful': successful_payments
            }
            title = "📊 <b>Общая статистика</b>"
        
        text = f"""
{title}

📈 <b>За выбранный период:</b>
• Заказов: {period_stats['orders']}
• Оплачено: ${period_stats['amount']:.2f}
• Успешных платежей: {period_stats['successful']}

📊 <b>За всё время:</b>
• Всего заказов: {total_orders}
• Всего получено: ${total_amount:.2f}
• Процент успешных: {(successful_payments/total_orders*100) if total_orders > 0 else 0:.1f}%

💡 Используйте кнопки для просмотра детальной статистики
        """
        
        await message.answer(text, reply_markup=admin_stats_keyboard())
    
    async def show_orders(self, message: Message, page: int = 0):
        """Показать список заказов"""
        user_id = message.from_user.id
        
        if user_id not in config.bot.admin_ids:
            return
        
        limit = 10
        offset = page * limit
        
        orders = self.db.get_recent_orders(days=30, limit=limit + 1)
        has_next = len(orders) > limit
        orders = orders[:limit]
        total_pages = (self._count_all_orders() + limit - 1) // limit
        
        if not orders:
            await message.answer(
                "📋 Заказов пока нет",
                reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 В админку", callback_data="admin:menu")
                .as_markup()
            )
            return
        
        text = f"📋 <b>Заказы (страница {page + 1}/{total_pages})</b>\n\n"
        
        for order in orders:
            status_emoji = {
                'pending': '⏳',
                'paid': '✅',
                'failed': '❌',
                'cancelled': '🚫',
                'expired': '⏰'
            }.get(order['status'], '📦')
            
            text += (
                f"{status_emoji} <b>#{order['order_id'][:12]}</b>\n"
                f"   👤 User: {order['user_id']}\n"
                f"   📦 {order['product_name']}\n"
                f"   💰 ${order['amount_usd']:.2f}\n"
                f"   🕐 {order['created_at'][:16]}\n\n"
            )
        
        await message.answer(text, reply_markup=admin_orders_keyboard(page, total_pages))
    
    async def show_order_detail(self, message_or_callback, order_id: str, is_callback: bool = False):
        """Показать детали заказа"""
        order = self.db.get_order(order_id)
        
        if not order:
            text = "❌ Заказ не найден"
            if is_callback:
                await message_or_callback.answer(text)
            else:
                await message_or_callback.answer(text)
            return
        
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

👤 <b>Пользователь:</b> {order['user_id']}
📦 <b>Товар:</b> {order['product_name']}
💵 <b>Сумма:</b> ${order['amount_usd']:.2f}
💰 <b>Криптовалюта:</b> {order['amount_crypto']} {order['currency']}
⛓️ <b>Сеть:</b> {order['network']}

🆔 <b>Invoice ID:</b> {order['invoice_id']}
📅 <b>Создан:</b> {order['created_at']}
        """
        
        if order['paid_at']:
            text += f"\n✅ <b>Оплачен:</b> {order['paid_at']}"
        
        keyboard = admin_order_detail_keyboard(order_id)
        
        if is_callback:
            if message_or_callback.message:
                await message_or_callback.message.edit_text(text, reply_markup=keyboard)
            else:
                await message_or_callback.answer(text, reply_markup=keyboard)
        else:
            await message_or_callback.answer(text, reply_markup=keyboard)
    
    async def show_pending_orders(self, message: Message):
        """Показать ожидающие заказы"""
        user_id = message.from_user.id
        
        if user_id not in config.bot.admin_ids:
            return
        
        orders = self.db.get_pending_orders(hours=24)
        
        if not orders:
            await message.answer(
                "⏳ Нет ожидающих заказов",
                reply_markup=admin_main_keyboard()
            )
            return
        
        text = f"⏳ <b>Ожидающие заказы ({len(orders)})</b>\n\n"
        
        for order in orders[:10]:
            text += (
                f"• <b>#{order['order_id'][:12]}</b> - "
                f"${order['amount_usd']:.2f} ({order['currency']})\n"
                f"  Создан: {order['created_at'][:16]}\n\n"
            )
        
        if len(orders) > 10:
            text += f"... и ещё {len(orders) - 10} заказов"
        
        await message.answer(text, reply_markup=admin_main_keyboard())
    
    async def manual_check_payment(self, message_or_callback, order_id: str, is_callback: bool = False):
        """Принудительная проверка платежа"""
        order = self.db.get_order(order_id)
        
        if not order:
            text = "❌ Заказ не найден"
            if is_callback:
                await message_or_callback.answer(text)
            else:
                await message_or_callback.answer(text)
            return
        
        if order['status'] != 'pending':
            text = f"⚠️ Заказ уже имеет статус: {order['status']}"
            if is_callback:
                await message_or_callback.answer(text)
            else:
                await message_or_callback.answer(text)
            return
        
        # Проверяем платёж
        payment = await self.cryptobot.check_payment(order['invoice_id'])
        
        if payment.is_paid:
            # Обновляем заказ
            self.db.update_order_status(order_id, 'paid', datetime.now().isoformat())
            self.db.update_user_stats(order['user_id'], order['amount_usd'])
            
            if not self.db.transaction_exists(order['invoice_id']):
                self.db.create_transaction(
                    invoice_id=order['invoice_id'],
                    order_id=order_id,
                    amount=payment.amount,
                    currency=payment.currency,
                    network=payment.network,
                    status='paid'
                )
            
            text = f"✅ <b>Платёж подтверждён!</b>\n\nЗаказ #{order_id[:12]} успешно оплачен."
            
            # Уведомляем пользователя
            try:
                await self.bot.send_message(
                    order['user_id'],
                    MESSAGES['payment_success'].format(
                        order_id=order_id,
                        amount=order['amount_usd'],
                        date=datetime.now().strftime('%d.%m.%Y %H:%M')
                    )
                )
            except Exception:
                pass
            
        else:
            status_text = {
                'active': 'в процессе',
                'expired': 'истёк',
                'cancelled': 'отменён'
            }.get(payment.raw_response.get('status', ''), payment.raw_response.get('status', 'неизвестен'))
            
            text = f"⏳ <b>Платёж {status_text}</b>\n\nЗаказ #{order_id[:12]} ещё не оплачен."
        
        if is_callback:
            if message_or_callback.message:
                await message_or_callback.message.edit_text(text)
            else:
                await message_or_callback.answer(text)
        else:
            await message_or_callback.answer(text)
    
    async def manual_confirm_order(self, callback: CallbackQuery, order_id: str):
        """Ручное подтверждение заказа"""
        order = self.db.get_order(order_id)
        
        if not order:
            await callback.answer("❌ Заказ не найден")
            return
        
        # Обновляем заказ
        self.db.update_order_status(order_id, 'paid', datetime.now().isoformat())
        self.db.update_user_stats(order['user_id'], order['amount_usd'])
        
        await callback.answer("✅ Заказ подтверждён!")
        
        # Показываем обновлённые детали
        await self.show_order_detail(callback, order_id, is_callback=True)
        
        # Уведомляем пользователя
        try:
            await self.bot.send_message(
                order['user_id'],
                MESSAGES['payment_success'].format(
                    order_id=order_id,
                    amount=order['amount_usd'],
                    date=datetime.now().strftime('%d.%m.%Y %H:%M')
                )
            )
        except Exception:
            pass
    
    async def manual_cancel_order(self, callback: CallbackQuery, order_id: str):
        """Ручная отмена заказа"""
        order = self.db.get_order(order_id)
        
        if not order:
            await callback.answer("❌ Заказ не найден")
            return
        
        # Обновляем заказ
        self.db.update_order_status(order_id, 'cancelled')
        
        await callback.answer("🚫 Заказ отменён")
        
        # Показываем обновлённые детали
        await self.show_order_detail(callback, order_id, is_callback=True)
    
    async def check_all_pending(self, message: Message):
        """Проверить все ожидающие платежи"""
        user_id = message.from_user.id
        
        if user_id not in config.bot.admin_ids:
            return
        
        orders = self.db.get_pending_orders(hours=24)
        
        if not orders:
            await message.answer(
                "✅ Нет ожидающих платежей для проверки",
                reply_markup=admin_main_keyboard()
            )
            return
        
        checked = 0
        confirmed = 0
        
        text = "🔄 <b>Проверка платежей</b>\n\n"
        
        for order in orders:
            try:
                payment = await self.cryptobot.check_payment(order['invoice_id'])
                
                if payment.is_paid:
                    self.db.update_order_status(order['order_id'], 'paid', datetime.now().isoformat())
                    self.db.update_user_stats(order['user_id'], order['amount_usd'])
                    
                    if not self.db.transaction_exists(order['invoice_id']):
                        self.db.create_transaction(
                            invoice_id=order['invoice_id'],
                            order_id=order['order_id'],
                            amount=payment.amount,
                            currency=payment.currency,
                            network=payment.network,
                            status='paid'
                        )
                    
                    confirmed += 1
                    
                    # Уведомляем пользователя
                    try:
                        await self.bot.send_message(
                            order['user_id'],
                            MESSAGES['payment_success'].format(
                                order_id=order['order_id'],
                                amount=order['amount_usd'],
                                date=datetime.now().strftime('%d.%m.%Y %H:%M')
                            )
                        )
                    except Exception:
                        pass
                
                checked += 1
                
                # Небольшая задержка между запросами
                await asyncio.sleep(0.5)
                
            except Exception as e:
                pass
        
        text += f"Проверено: {checked}\nПодтверждено: {confirmed}"
        
        await message.answer(text, reply_markup=admin_main_keyboard())
    
    async def cleanup_database(self, message: Message, cleanup_type: str):
        """Очистка базы данных"""
        user_id = message.from_user.id
        
        if user_id not in config.bot.admin_ids:
            return
        
        if cleanup_type == 'old':
            deleted = self.db.delete_old_orders(7)
            await message.answer(
                f"🧹 Удалено {deleted} старых заказов",
                reply_markup=admin_main_keyboard()
            )
        elif cleanup_type == 'vacuum':
            deleted = self.db.cleanup_database()
            await message.answer(
                f"📦 База данных оптимизирована\nУдалено записей: {deleted}",
                reply_markup=admin_main_keyboard()
            )
    
    async def show_balance(self, message: Message):
        """Показать баланс CryptoBot"""
        user_id = message.from_user.id
        
        if user_id not in config.bot.admin_ids:
            return
        
        try:
            balance = await self.cryptobot.get_balance()
            
            text = "💰 <b>Баланс приложения</b>\n\n"
            
            for asset in balance.get('balance', []):
                text += f"• {asset['currency']}: {asset['available']}\n"
            
            await message.answer(text, reply_markup=admin_main_keyboard())
            
        except Exception as e:
            await message.answer(
                f"❌ Ошибка получения баланса: {str(e)}",
                reply_markup=admin_main_keyboard()
            )
    
    async def toggle_notifications(self, callback: CallbackQuery):
        """Переключить уведомления"""
        self.notifications_enabled = not self.notifications_enabled
        
        status = "включены" if self.notifications_enabled else "выключены"
        await callback.answer(f"🔔 Уведомления {status}")
    
    # ============ Вспомогательные методы ============
    
    def _get_period_stats(self, period: str) -> Dict[str, Any]:
        """Получить статистику за период"""
        daily_stats = self.db.get_daily_stats(days=30)
        
        if period == 'today':
            stats = self.db.get_stats()
            return {
                'orders': stats.get('today_orders', 0) or 0,
                'amount': stats.get('today_amount', 0) or 0,
                'successful': stats.get('today_paid', 0) or 0
            }
        
        elif period == 'week':
            week_ago = datetime.now() - timedelta(days=7)
            week_stats = [d for d in daily_stats if datetime.strptime(d['date'], '%Y-%m-%d') >= week_ago]
            
            return {
                'orders': sum(d['orders'] for d in week_stats),
                'amount': sum(d['amount'] for d in week_stats),
                'successful': sum(1 for d in week_stats if d['amount'] > 0)
            }
        
        elif period == 'month':
            month_ago = datetime.now() - timedelta(days=30)
            month_stats = [d for d in daily_stats if datetime.strptime(d['date'], '%Y-%m-%d') >= month_ago]
            
            return {
                'orders': sum(d['orders'] for d in month_stats),
                'amount': sum(d['amount'] for d in month_stats),
                'successful': sum(1 for d in month_stats if d['amount'] > 0)
            }
        
        return {'orders': 0, 'amount': 0, 'successful': 0}
    
    def _count_all_orders(self) -> int:
        """Подсчитать общее количество заказов"""
        orders = self.db.get_recent_orders(days=365, limit=10000)
        return len(orders)


# ============ Генерация отчётов ============

def generate_daily_report(db: Database) -> str:
    """Сгенерировать дневной отчёт"""
    stats = db.get_stats()
    daily = db.get_daily_stats(days=1)
    
    if daily:
        day_stats = daily[0]
    else:
        day_stats = {'orders': 0, 'amount': 0}
    
    report = f"""
📅 <b>Дневной отчёт</b>
📅 {datetime.now().strftime('%d.%m.%Y')}

💰 <b>За сегодня:</b>
• Новых заказов: {day_stats['orders']}
• Получено: ${day_stats['amount']:.2f}

📊 <b>Общая статистика:</b>
• Всего заказов: {stats['total_orders']}
• Всего получено: ${stats['total_amount']:.2f}
• Успешных платежей: {stats['successful_payments']}

💵 <b>Средний чек:</b>
• ${(stats['total_amount']/stats['successful_payments']) if stats['successful_payments'] > 0 else 0:.2f}
    """
    
    return report


def generate_weekly_report(db: Database) -> str:
    """Сгенерировать недельный отчёт"""
    stats = db.get_stats()
    weekly_stats = db.get_daily_stats(days=7)
    
    total_orders = sum(d['orders'] for d in weekly_stats)
    total_amount = sum(d['amount'] for d in weekly_stats)
    successful_days = sum(1 for d in weekly_stats if d['amount'] > 0)
    
    report = f"""
📊 <b>Недельный отчёт</b>
📅 {datetime.now().strftime('%d.%m.%Y')}

💰 <b>За неделю:</b>
• Новых заказов: {total_orders}
• Получено: ${total_amount:.2f}
• Дней с платежами: {successful_days}/7

📈 <b>Среднее за день:</b>
• ${(total_amount/successful_days) if successful_days > 0 else 0:.2f}

📊 <b>Общая статистика:</b>
• Всего заказов: {stats['total_orders']}
• Всего получено: ${stats['total_amount']:.2f}
    """
    
    return report


def generate_payment_report(db: Database) -> str:
    """Сгенерировать отчёт по платежам"""
    stats = db.get_stats()
    transactions = db.get_transactions(limit=100)
    
    # Группируем по валютам
    by_currency = {}
    for t in transactions:
        curr = t['currency']
        if curr not in by_currency:
            by_currency[curr] = {'count': 0, 'amount': 0}
        by_currency[curr]['count'] += 1
        by_currency[curr]['amount'] += t['amount']
    
    report = f"""
💰 <b>Отчёт по платежам</b>

📊 <b>По валютам:</b>
"""
    
    for currency, data in by_currency.items():
        report += f"• {currency}: {data['count']} платежей (${data['amount']:.2f})\n"
    
    report += f"""
📈 <b>Общая статистика:</b>
• Всего платежей: {len(transactions)}
• Общая сумма: ${stats['total_amount']:.2f}
• Успешных: {stats['successful_payments']}
    """
    
    return report


def generate_users_report(db: Database) -> str:
    """Сгенерировать отчёт по пользователям"""
    top_users = db.get_top_users(10)
    stats = db.get_stats()
    
    report = f"""
👥 <b>Отчёт по пользователям</b>

🏆 <b>Топ покупатели:</b>
"""
    
    for i, user in enumerate(top_users, 1):
        report += f"{i}. User {user['user_id']} - ${user['total_spent']:.2f} ({user['orders_count']} заказов)\n"
    
    report += f"""
📊 <b>Общая статистика:</b>
• Всего пользователей: {stats['total_orders']}
• Средний чек: ${(stats['total_amount']/stats['successful_payments']) if stats['successful_payments'] > 0 else 0:.2f}
    """
    
    return report
