#!/bin/bash
# Скрипт для загрузки бота на GitHub
# Автор: MiniMax Agent

echo "🚀 Загрузка бота на GitHub..."
echo ""

# Переходим в папку с ботом
cd /workspace/crypto_payment_bot

# Переименовываем ветку в main
git branch -M main

# Подключаем удалённый репозиторий
git remote add origin https://github.com/Kristine79/Tgbot.git

# Загружаем на GitHub
echo "📤 Выполняется git push..."
echo ""
echo "⚠️  Введите ваш GitHub логин и пароль (или Personal Access Token)"
echo ""

git push -u origin main

echo ""
echo "✅ Готово! Репозиторий обновлён."
