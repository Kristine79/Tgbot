#!/usr/bin/env python3
"""
Запуск веб-сервера для вебхуков
Используется для обработки уведомлений от CryptoBot в реальном времени
"""

import os
import sys
import logging
import argparse
from threading import Thread

# Добавление текущей директории в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config
from database import Database
from webhook import create_webhook_handler, register_webhook, delete_webhook, get_webhook_info
from main import bot, config as main_config

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(description='Webhook сервер для CryptoPayment Bot')
    
    parser.add_argument('--setup', action='store_true',
                        help='Зарегистрировать вебхук в CryptoBot')
    parser.add_argument('--delete', action='store_true',
                        help='Удалить вебхук из CryptoBot')
    parser.add_argument('--info', action='store_true',
                        help='Показать информацию о вебхуке')
    parser.add_argument('--port', type=int, default=None,
                        help='Порт для запуска сервера')
    parser.add_argument('--host', type=str, default=None,
                        help='Хост для запуска сервера')
    
    return parser.parse_args()


def setup_webhook():
    """Регистрация вебхука"""
    print("🔗 Регистрация вебхука в CryptoBot...")
    
    success = register_webhook(
        bot_token=config.bot.token,
        webhook_url=config.webhook.webhook_host + config.webhook.webhook_path
    )
    
    if success:
        print("✅ Вебхук успешно зарегистрирован!")
        print(f"   URL: {config.webhook.webhook_host}{config.webhook.webhook_path}")
    else:
        print("❌ Ошибка регистрации вебхука")
    
    return success


def remove_webhook():
    """Удаление вебхука"""
    print("🗑️ Удаление вебхука из CryptoBot...")
    
    success = delete_webhook(config.bot.token)
    
    if success:
        print("✅ Вебхук успешно удалён!")
    else:
        print("❌ Ошибка удаления вебхука")
    
    return success


def show_webhook_info():
    """Показать информацию о вебхуке"""
    print("📋 Информация о вебхуке:")
    
    info = get_webhook_info(config.bot.token)
    
    if info:
        print(f"   URL: {info.get('url', 'не задан')}")
        print(f"   Статус: {'активен' if info.get('is_enabled') else 'неактивен'}")
        print(f"   Секрет: {'установлен' if info.get('secret') else 'не установлен'}")
    else:
        print("   Не удалось получить информацию")


def run_server(host: str, port: int):
    """Запуск веб-сервера"""
    # Инициализация базы данных
    db = Database(config.database.db_path)
    
    # Создание обработчика вебхуков
    webhook_handler = create_webhook_handler(
        db=db,
        bot_token=config.bot.token,
        admin_ids=config.bot.admin_ids
    )
    
    print("🚀 Запуск веб-сервера...")
    print(f"   Хост: {host}")
    print(f"   Порт: {port}")
    print(f"   URL: {config.webhook.webhook_host}{config.webhook.webhook_path}")
    print()
    
    try:
        webhook_handler.run(host=host, port=port)
    except KeyboardInterrupt:
        print("\n👋 Сервер остановлен")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1)


def main():
    """Главная функция"""
    args = parse_args()
    
    # Настройка из переменных окружения
    host = args.host or config.webhook.listen_host
    port = args.port or config.webhook.listen_port
    
    if args.setup:
        sys.exit(0 if setup_webhook() else 1)
    
    elif args.delete:
        sys.exit(0 if remove_webhook() else 1)
    
    elif args.info:
        show_webhook_info()
    
    else:
        # Проверка SSL для продакшена
        if not config.webhook.webhook_host.startswith('https://'):
            print("⚠️  ВНИМАНИЕ: Для продакшена рекомендуется использовать HTTPS!")
            print("   Установите SSL-сертификат (например, Let's Encrypt)")
            print()
        
        run_server(host, port)


if __name__ == '__main__':
    main()
