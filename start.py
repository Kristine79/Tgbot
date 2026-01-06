#!/usr/bin/env python3
"""
Быстрый запуск бота
Создаёт конфигурацию и запускает бота
"""

import os
import sys
import subprocess

def check_python_version():
    """Проверка версии Python"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print(f"❌ Требуется Python 3.10+. У вас: {version.major}.{version.minor}")
        sys.exit(1)
    print(f"✅ Python {version.major}.{version.minor}.{version.micro}")

def check_dependencies():
    """Проверка и установка зависимостей"""
    print("📦 Проверка зависимостей...")
    
    try:
        import aiogram
        import flask
        import aiohttp
        print("✅ Все зависимости установлены")
        return True
    except ImportError as e:
        print(f"❌ Отсутствует: {e.name}")
        print("📦 Устанавливаю зависимости...")
        
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
            print("✅ Зависимости установлены")
            return True
        except subprocess.CalledProcessError:
            print("❌ Ошибка установки зависимостей")
            return False

def check_env_file():
    """Проверка наличия .env файла"""
    if not os.path.exists('.env'):
        print("📝 Создаю файл .env из шаблона...")
        
        if os.path.exists('.env.example'):
            with open('.env.example', 'r') as f:
                content = f.read()
            
            with open('.env', 'w') as f:
                f.write(content)
            
            print("✅ Создан файл .env")
            print("\n⚠️  ВАЖНО: Отредактируйте файл .env и заполните:")
            print("   - BOT_TOKEN (токен Telegram бота)")
            print("   - CRYPTOBOT_API_TOKEN (API токен CryptoBot)")
            print("   - ADMIN_IDS (ваш Telegram ID)")
            print()
        else:
            print("❌ Файл .env.example не найден")
    else:
        print("✅ Файл .env найден")

def check_env_values():
    """Проверка заполнения обязательных полей"""
    from dotenv import load_dotenv
    load_dotenv()
    
    errors = []
    
    if not os.getenv('BOT_TOKEN') or BOT_TOKEN == 'your_telegram_bot_token_here':
        errors.append("BOT_TOKEN")
    
    if not os.getenv('CRYPTOBOT_API_TOKEN') or os.getenv('CRYPTOBOT_API_TOKEN') == 'your_cryptobot_api_token_here':
        errors.append("CRYPTOBOT_API_TOKEN")
    
    if not os.getenv('ADMIN_IDS') or os.getenv('ADMIN_IDS') == '123456789,987654321':
        errors.append("ADMIN_IDS")
    
    if errors:
        print("⚠️  В файле .env не заполнены обязательные поля:")
        for field in errors:
            print(f"   - {field}")
        print("\n📝 Отредактируйте файл .env и перезапустите бота")
        return False
    
    print("✅ Все обязательные поля заполнены")
    return True

def main():
    """Главная функция"""
    print("=" * 50)
    print("🚀 Telegram CryptoPayment Bot")
    print("=" * 50)
    print()
    
    # Проверка Python
    check_python_version()
    print()
    
    # Проверка зависимостей
    if not check_dependencies():
        sys.exit(1)
    print()
    
    # Проверка .env
    check_env_file()
    print()
    
    # Проверка значений
    if not check_env_values():
        print("\n❌ Запуск отменён из-за незаполненных полей в .env")
        sys.exit(1)
    print()
    
    print("=" * 50)
    print("✅ Все проверки пройдены!")
    print("=" * 50)
    print()
    print("🚀 Запускаю бота...")
    print()
    
    # Запуск бота
    try:
        import main
        asyncio.run(main.main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
