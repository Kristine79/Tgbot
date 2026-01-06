"""
Конфигурационный файл для Telegram-бота с CryptoBot
Все настройки приложения хранятся здесь
"""

import os
from dataclasses import dataclass
from typing import List


@dataclass
class BotConfig:
    """Конфигурация Telegram-бота"""
    token: str = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    admin_ids: List[int] = [int(x) for x in os.getenv("ADMIN_IDS", "123456789,987654321").split(",")]
    support_username: str = os.getenv("SUPPORT_USERNAME", "support_username")


@dataclass
class CryptoBotConfig:
    """Конфигурация CryptoBot API"""
    api_token: str = os.getenv("CRYPTOBOT_API_TOKEN", "YOUR_CRYPTOBOT_API_TOKEN")
    api_url: str = os.getenv("CRYPTOBOT_API_URL", "https://pay.crypt.bot/api/")
    app_id: str = os.getenv("CRYPTOBOT_APP_ID", "A511773")


@dataclass
class DatabaseConfig:
    """Конфигурация базы данных"""
    db_path: str = os.getenv("DB_PATH", "payments.db")


@dataclass
class WebhookConfig:
    """Конфигурация вебхука"""
    webhook_host: str = os.getenv("WEBHOOK_HOST", "https://your-domain.com")
    webhook_path: str = os.getenv("WEBHOOK_PATH", "/webhook")
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "your_webhook_secret_key")
    listen_host: str = os.getenv("LISTEN_HOST", "0.0.0.0")
    listen_port: int = int(os.getenv("PORT", os.getenv("LISTEN_PORT", "8080")))


@dataclass
class Config:
    """Общая конфигурация приложения"""
    bot: BotConfig
    cryptobot: CryptoBotConfig
    database: DatabaseConfig
    webhook: WebhookConfig
    
    @classmethod
    def from_env(cls) -> "Config":
        """Создать конфигурацию из переменных окружения"""
        return cls(
            bot=BotConfig(),
            cryptobot=CryptoBotConfig(),
            database=DatabaseConfig(),
            webhook=WebhookConfig()
        )


# Создаём глобальный экземпляр конфигурации
config = Config.from_env()

# Настройки валют и платежей
SUPPORTED_CURRENCIES = {
    "USDT": ["TON", "ETH", "TRX", "BEP20"],
    "BTC": ["BTC"],
    "ETH": ["ETH"],
    "USDC": ["ETH", "TRX"],
    "TON": ["TON"],
    "TRX": ["USDT"]
}

# Названия товаров/услуг
PRODUCTS = {
    "basic": {"name": "Базовый тариф", "price_usd": 9.99},
    "standard": {"name": "Стандартный тариф", "price_usd": 29.99},
    "premium": {"name": "Премиум тариф", "price_usd": 99.99},
    "custom": {"name": "Индивидуальный заказ", "price_usd": 0}
}

# Тексты сообщений
MESSAGES = {
    "welcome": """
🔐 <b>Добро пожаловать в CryptoPay Bot!</b>

Здесь вы можете безопасно оплатить товары и услуги с помощью криптовалюты.

💰 <b>Доступные способы оплаты:</b>
• USDT (TON, ETH, TRX, BEP20)
• BTC
• ETH
• USDC
• TON
• TRX

📦 <b>Выберите товар:</b>
""",
    
    "select_payment": """
💳 <b>Создание платежа</b>

Товар: <b>{product_name}</b>
Сумма: <b>${price}</b>

Выберите криптовалюту для оплаты:
""",
    
    "payment_created": """
✅ <b>Платёж создан!</b>

🛒 <b>Заказ #{order_id}</b>
Товар: {product_name}
Сумма: ${amount}

💰 <b>Реквизиты для оплаты:</b>
{payment_details}

⚠️ <b>Важно:</b>
• Отправьте точную сумму
• Оплата должна быть произведена в сети {network}
• После оплаты нажмите "Проверить платёж"

💬 Возникли вопросы: @{support}
""",
    
    "payment_pending": """
⏳ <b>Платёж в обработке</b>

Заказ #{order_id} ожидает подтверждения оплаты.
Пожалуйста, дождитесь поступления средств.

🕐 Ожидаемое время: 1-30 минут
""",
    
    "payment_success": """
🎉 <b>Платёж успешно получен!</b>

✅ Заказ #{order_id} оплачен
💰 Сумма: ${amount}
📅 Дата: {date}

Спасибо за покупку! 🎁
""",
    
    "payment_failed": """
❌ <b>Платёж не найден</b>

Заказ #{order_id} не был оплачен или истёк срок действия счёта.

🔄 Хотите создать новый платёж?
""",
    
    "order_history": """
📋 <b>История заказов</b>

Всего заказов: {total_orders}
Оплачено: {paid_orders}
Ожидает: {pending_orders}
""",
    
    "admin_stats": """
📊 <b>Статистика</b>

💰 <b>За сегодня:</b>
• Заказов: {today_orders}
• Получено: ${today_amount}

📈 <b>За всё время:</b>
• Всего заказов: {total_orders}
• Всего получено: ${total_amount}
• Успешных платежей: {successful_payments}
""",
    
    "help_text": """
❓ <b>Помощь</b>

/start - Запустить бота
/menu - Главное меню
/history - История заказов
/help - Помощь

💬 Поддержка: @{support}
"""
}
