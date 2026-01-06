#!/usr/bin/env python3
"""
Вебхук-сервер для Railway
Запускает Flask-сервер для обработки вебхуков от CryptoBot

Использование:
    python railway_webhook.py

Для Railway это основной процесс, который должен быть запущен.
"""

import os
import sys

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webhook import create_webhook_handler, register_webhook, get_webhook_info
from config import config
from database import Database

# Настройка логирования
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Основная функция запуска веб-сервера"""
    logger.info("=" * 50)
    logger.info("🚀 Запуск CryptoPay Webhook Server")
    logger.info("=" * 50)
    
    # Инициализация базы данных
    logger.info("📦 Инициализация базы данных...")
    db_path = os.getenv('DB_PATH', 'payments.db')
    db = Database(db_path)
    logger.info("✅ База данных готова")
    
    # Проверка конфигурации
    api_token = config.cryptobot.api_token
    bot_token = config.bot.token
    
    if not api_token or api_token == 'YOUR_CRYPTOBOT_API_TOKEN':
        logger.warning("⚠️  CRYPTOBOT_API_TOKEN не настроен!")
        logger.info("   Установите переменную окружения CRYPTOBOT_API_TOKEN")
    
    if not bot_token or bot_token == 'YOUR_BOT_TOKEN_HERE':
        logger.warning("⚠️  BOT_TOKEN не настроен!")
        logger.info("   Установите переменную окружения BOT_TOKEN")
    
    # Создание обработчика вебхуков
    logger.info("🔗 Создание обработчика вебхуков...")
    webhook_handler = create_webhook_handler(
        db=db,
        cryptobot_api_token=api_token,
        bot_token=bot_token,
        admin_ids=config.bot.admin_ids
    )
    
    # Получение URL вебхука
    webhook_url = os.getenv('WEBHOOK_HOST', '') + os.getenv('WEBHOOK_PATH', '/webhook')
    
    if webhook_url and webhook_url != 'https://your-domain.com/webhook':
        logger.info(f"📝 URL вебхука: {webhook_url}")
        
        # Регистрация вебхука
        logger.info("🔗 Регистрация вебхука в CryptoBot...")
        if register_webhook(webhook_url):
            logger.info("✅ Вебхук зарегистрирован!")
        else:
            logger.warning("⚠️  Не удалось зарегистрировать вебхук")
    
    # Информация о приложении
    logger.info("📋 Информация о приложении:")
    app_info = get_webhook_info()
    if app_info:
        logger.info(f"   ID: {app_info.get('id', 'N/A')}")
        logger.info(f"   Имя: {app_info.get('name', 'N/A')}")
    else:
        logger.warning("   Не удалось получить информацию о приложении")
    
    # Запуск сервера
    # Railway автоматически устанавливает переменную $PORT
    host = os.getenv('LISTEN_HOST', '0.0.0.0')
    port = int(os.getenv('PORT', os.getenv('LISTEN_PORT', '8080')))
    
    logger.info("=" * 50)
    logger.info(f"🌐 Запуск сервера на {host}:{port}")
    logger.info("   Эндпоинты:")
    logger.info(f"   - / (индекс)")
    logger.info(f"   - /health (проверка состояния)")
    logger.info(f"   - /api/status/<order_id> (статус заказа)")
    logger.info(f"   - {os.getenv('WEBHOOK_PATH', '/webhook')} (вебхук)")
    logger.info("=" * 50)
    
    try:
        webhook_handler.run(host=host, port=port)
    except KeyboardInterrupt:
        logger.info("👋 Сервер остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска сервера: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
