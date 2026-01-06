"""
Модуль работы с базой данных SQLite
Хранит информацию о пользователях, заказах и платежах
"""

import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from dataclasses import dataclass, asdict


@dataclass
class Order:
    """Структура заказа"""
    id: int
    user_id: int
    product_id: str
    product_name: str
    amount_usd: float
    amount_crypto: float
    currency: str
    network: str
    invoice_id: str
    payment_url: str
    status: str
    created_at: str
    paid_at: Optional[str] = None
    extra_data: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в словарь"""
        return asdict(self)


class Database:
    """Класс для работы с базой данных"""
    
    def __init__(self, db_path: str = "payments.db"):
        self.db_path = db_path
        self.init_db()
    
    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для соединения с БД"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_db(self):
        """Инициализация структуры базы данных"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language_code TEXT DEFAULT 'ru',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    total_spent REAL DEFAULT 0.0,
                    orders_count INTEGER DEFAULT 0
                )
            """)
            
            # Таблица заказов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT UNIQUE,
                    user_id INTEGER,
                    product_id TEXT,
                    product_name TEXT,
                    amount_usd REAL,
                    amount_crypto REAL,
                    currency TEXT,
                    network TEXT,
                    invoice_id TEXT,
                    payment_url TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    paid_at TEXT,
                    extra_data TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Таблица платежей (транзакции)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_id TEXT,
                    order_id TEXT,
                    amount REAL,
                    currency TEXT,
                    network TEXT,
                    status TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    processed_at TEXT
                )
            """)
            
            # Индексы для быстрого поиска
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_user_id 
                ON orders(user_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_status 
                ON orders(status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_created_at 
                ON orders(created_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_transactions_invoice_id 
                ON transactions(invoice_id)
            """)
            
            conn.commit()
    
    # ============ Операции с пользователями ============
    
    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить пользователя по ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_or_create_user(self, user_id: int, username: str = None, 
                           first_name: str = None, last_name: str = None,
                           language_code: str = 'ru') -> Dict[str, Any]:
        """Получить или создать пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            
            cursor.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, language_code)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, first_name, last_name, language_code))
            
            return self.get_user(user_id)
    
    def update_user_stats(self, user_id: int, amount: float):
        """Обновить статистику пользователя после платежа"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET total_spent = total_spent + ?,
                    orders_count = orders_count + 1
                WHERE user_id = ?
            """, (amount, user_id))
    
    def get_top_users(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получить топ пользователей по тратам"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM users 
                ORDER BY total_spent DESC 
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    # ============ Операции с заказами ============
    
    def create_order(self, order: Order) -> Order:
        """Создать новый заказ"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO orders (
                    order_id, user_id, product_id, product_name,
                    amount_usd, amount_crypto, currency, network,
                    invoice_id, payment_url, status, extra_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order.order_id, order.user_id, order.product_id,
                order.product_name, order.amount_usd, order.amount_crypto,
                order.currency, order.network, order.invoice_id,
                order.payment_url, order.status, order.extra_data
            ))
            order.id = cursor.lastrowid
            return order
    
    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Получить заказ по ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_order_by_invoice(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """Получить заказ по invoice_id"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE invoice_id = ?", (invoice_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_user_orders(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Получить заказы пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM orders 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def update_order_status(self, order_id: str, status: str, paid_at: str = None):
        """Обновить статус заказа"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if paid_at:
                cursor.execute("""
                    UPDATE orders 
                    SET status = ?, paid_at = ?
                    WHERE order_id = ?
                """, (status, paid_at, order_id))
            else:
                cursor.execute("""
                    UPDATE orders 
                    SET status = ?
                    WHERE order_id = ?
                """, (status, order_id))
    
    def get_orders_by_status(self, status: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Получить заказы по статусу"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM orders 
                WHERE status = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (status, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_pending_orders(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Получить ожидающие заказы за последние N часов"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM orders 
                WHERE status = 'pending' 
                AND datetime(created_at) >= datetime('now', ?)
                ORDER BY created_at ASC
            """, (f'-{hours} hours',))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_recent_orders(self, days: int = 7, limit: int = 100) -> List[Dict[str, Any]]:
        """Получить недавние заказы"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM orders 
                WHERE datetime(created_at) >= datetime('now', ?)
                ORDER BY created_at DESC 
                LIMIT ?
            """, (f'-{days} days', limit))
            return [dict(row) for row in cursor.fetchall()]
    
    # ============ Статистика ============
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить общую статистику"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Общая статистика
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_orders,
                    SUM(CASE WHEN status = 'paid' THEN amount_usd ELSE 0 END) as total_amount,
                    SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) as successful_payments,
                    COUNT(CASE WHEN status = 'paid' THEN 1 END) as paid_orders
                FROM orders
            """)
            total_stats = dict(cursor.fetchone())
            
            # Статистика за сегодня
            cursor.execute("""
                SELECT 
                    COUNT(*) as today_orders,
                    SUM(CASE WHEN status = 'paid' THEN amount_usd ELSE 0 END) as today_amount,
                    COUNT(CASE WHEN status = 'paid' THEN 1 END) as today_paid
                FROM orders
                WHERE date(created_at) = date('now')
            """)
            today_stats = dict(cursor.fetchone())
            
            # Статистика за текущий месяц
            cursor.execute("""
                SELECT 
                    COUNT(*) as month_orders,
                    SUM(CASE WHEN status = 'paid' THEN amount_usd ELSE 0 END) as month_amount
                FROM orders
                WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
            """)
            month_stats = dict(cursor.fetchone())
            
            return {
                **total_stats,
                **today_stats,
                **month_stats
            }
    
    def get_daily_stats(self, days: int = 30) -> List[Dict[str, Any]]:
        """Получить статистику по дням"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    date(created_at) as date,
                    COUNT(*) as orders,
                    SUM(CASE WHEN status = 'paid' THEN amount_usd ELSE 0 END) as amount
                FROM orders
                WHERE datetime(created_at) >= datetime('now', ?)
                GROUP BY date(created_at)
                ORDER BY date DESC
            """, (f'-{days} days',))
            return [dict(row) for row in cursor.fetchall()]
    
    # ============ Операции с транзакциями ============
    
    def create_transaction(self, invoice_id: str, order_id: str, amount: float,
                          currency: str, network: str, status: str) -> int:
        """Создать запись о транзакции"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO transactions (invoice_id, order_id, amount, currency, network, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (invoice_id, order_id, amount, currency, network, status))
            return cursor.lastrowid
    
    def get_transactions(self, order_id: str = None, invoice_id: str = None,
                        limit: int = 100) -> List[Dict[str, Any]]:
        """Получить транзакции"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if order_id:
                cursor.execute("""
                    SELECT * FROM transactions 
                    WHERE order_id = ?
                    ORDER BY created_at DESC 
                    LIMIT ?
                """, (order_id, limit))
            elif invoice_id:
                cursor.execute("""
                    SELECT * FROM transactions 
                    WHERE invoice_id = ?
                    ORDER BY created_at DESC 
                    LIMIT ?
                """, (invoice_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM transactions 
                    ORDER BY created_at DESC 
                    LIMIT ?
                """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def transaction_exists(self, invoice_id: str) -> bool:
        """Проверить существует ли транзакция"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM transactions WHERE invoice_id = ? LIMIT 1", (invoice_id,))
            return cursor.fetchone() is not None
    
    # ============ Утилиты ============
    
    def delete_old_orders(self, days: int = 30) -> int:
        """Удалить старые отменённые заказы"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM orders 
                WHERE status = 'cancelled'
                AND datetime(created_at) < datetime('now', ?)
            """, (f'-{days} days',))
            return cursor.rowcount
    
    def cleanup_database(self):
        """Очистка базы данных"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Оптимизация
            cursor.execute("VACUUM")
            
            # Удаление старых отменённых заказов
            deleted = self.delete_old_orders(7)
            
            return deleted
    
    def close(self):
        """Закрыть соединение"""
        pass  # Соединения закрываются через контекстный менеджер


# Утилита для форматирования заказов
def format_order_list(orders: List[Dict[str, Any]]) -> str:
    """Форматировать список заказов для отображения"""
    if not orders:
        return "Заказов пока нет"
    
    lines = []
    for order in orders[:20]:  # Ограничиваем 20 заказами
        status_emoji = {
            'pending': '⏳',
            'paid': '✅',
            'failed': '❌',
            'cancelled': '🚫',
            'expired': '⏰'
        }.get(order['status'], '📦')
        
        lines.append(
            f"{status_emoji} <b>Заказ #{order['order_id'][:8]}</b>\n"
            f"   Товар: {order['product_name']}\n"
            f"   Сумма: ${order['amount_usd']:.2f}\n"
            f"   Дата: {order['created_at'][:10]}\n"
        )
    
    return '\n'.join(lines)
