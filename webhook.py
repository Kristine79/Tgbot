"""
Вебхук для приёма уведомлений от CryptoBot
Запускается как отдельное Flask-приложение
Обновлено согласно официальной документации: https://help.send.tg/en/articles/10279948-crypto-pay-api#webhooks
"""

import os
import hmac
import hashlib
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify
from threading import Thread

from config import config
from database import Database
from cryptobot import PaymentStatus, verify_webhook_signature, WebhookUpdate

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CryptoBotWebhookHandler:
    """
    Класс для обработки вебхуков CryptoBot
    Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#webhooks
    """
    
    def __init__(self, db: Database, cryptobot_api_token: str, bot_token: str, admin_ids: list):
        self.db = db
        self.cryptobot_api_token = cryptobot_api_token
        self.bot_token = bot_token
        self.admin_ids = admin_ids
        self.app = Flask(__name__)
        self._setup_routes()
    
    def _setup_routes(self):
        """Настроить маршруты Flask"""
        
        @self.app.route('/')
        def index():
            return 'CryptoPay Bot Webhook Server'
        
        @self.app.route('/health')
        def health():
            return jsonify({
                'status': 'ok', 
                'timestamp': datetime.now().isoformat()
            })
        
        @self.app.route('/api/status/<order_id>')
        def check_order_status(order_id: str):
            """API для проверки статуса заказа"""
            order = self.db.get_order(order_id)
            if order:
                return jsonify({
                    'status': order['status'],
                    'amount': order['amount_usd'],
                    'product': order['product_name']
                })
            return jsonify({'error': 'Order not found'}), 404
        
        @self.app.route(config.webhook_path, methods=['POST'])
        def webhook():
            """Обработка входящих вебхуков"""
            return self._handle_webhook(request)
    
    def _handle_webhook(self, flask_request) -> tuple:
        """
        Обработать входящий вебхук
        Структура вебхука согласно документации:
        {
            "update_id": 12345,
            "update_type": "invoice_paid",
            "request_date": "2024-01-01T12:00:00Z",
            "payload": { /* Invoice object */ }
        }
        """
        try:
            # Получаем тело запроса
            body = flask_request.get_data()
            
            # Получаем подпись из заголовка
            signature = flask_request.headers.get('crypto-pay-api-signature', '')
            
            # Проверяем подпись (рекомендуется в продакшене)
            if signature:
                if not verify_webhook_signature(self.cryptobot_api_token, body, signature):
                    logger.warning("Invalid webhook signature")
                    # В продакшене можно возвращать 401:
                    # return jsonify({'error': 'Invalid signature'}), 401
            
            # Парсим JSON
            payload = json.loads(body)
            
            # Логируем
            logger.info(f"Received webhook: update_type={payload.get('update_type')}")
            
            # Проверяем тип обновления
            update_type = payload.get('update_type')
            
            if update_type == 'invoice_paid':
                return self._handle_invoice_paid(payload)
            else:
                logger.info(f"Unknown update type: {update_type}")
                return jsonify({'status': 'ignored'}), 200
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in webhook: {e}")
            return jsonify({'error': 'Invalid JSON'}), 400
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return jsonify({'error': str(e)}), 500
    
    def _handle_invoice_paid(self, payload: Dict[str, Any]) -> tuple:
        """
        Обработать событие оплаты счёта (invoice_paid)
        
        Payload содержит Invoice object согласно документации
        """
        try:
            invoice_data = payload.get('payload', {})
            
            if not invoice_data:
                logger.error("No invoice data in payload")
                return jsonify({'error': 'No invoice data'}), 400
            
            # Получаем ID счёта и payload (order_id)
            invoice_id = invoice_data.get('invoice_id')
            order_id = invoice_data.get('payload', '')
            
            logger.info(f"Processing invoice_paid: invoice_id={invoice_id}, order_id={order_id}")
            
            if not invoice_id:
                logger.error("No invoice_id in payload")
                return jsonify({'error': 'No invoice_id'}), 400
            
            # Проверяем, что заказ существует
            order = None
            
            if order_id:
                # Ищем по order_id (payload)
                order = self.db.get_order(order_id)
            
            if not order:
                # Ищем по invoice_id
                order = self.db.get_order_by_invoice(str(invoice_id))
            
            if not order:
                logger.error(f"Order not found for invoice: {invoice_id}")
                return jsonify({'error': 'Order not found'}), 404
            
            # Проверяем, что платёж ещё не обработан
            if order['status'] == 'paid':
                logger.info(f"Order {order['order_id']} already paid")
                return jsonify({'status': 'already_processed'}), 200
            
            # Обновляем статус заказа
            self.db.update_order_status(
                order['order_id'], 
                'paid', 
                datetime.now().isoformat()
            )
            
            # Обновляем статистику пользователя
            self.db.update_user_stats(order['user_id'], order['amount_usd'])
            
            # Создаём запись о транзакции
            if not self.db.transaction_exists(str(invoice_id)):
                self.db.create_transaction(
                    invoice_id=str(invoice_id),
                    order_id=order['order_id'],
                    amount=float(invoice_data.get('amount', order['amount_usd'])),
                    currency=invoice_data.get('asset', order['currency']),
                    network='',  # В новом API поле network не возвращается
                    status='paid'
                )
            
            # Отправляем уведомление пользователю
            self._send_notification(order, 'success', invoice_data)
            
            logger.info(f"Order {order['order_id']} successfully processed")
            return jsonify({'status': 'ok'}), 200
            
        except Exception as e:
            logger.error(f"Error processing invoice_paid: {e}")
            return jsonify({'error': str(e)}), 500
    
    def _handle_invoice_expired(self, payload: Dict[str, Any]) -> tuple:
        """
        Обработать истечение срока счёта
        """
        try:
            invoice_data = payload.get('payload', {})
            invoice_id = invoice_data.get('invoice_id')
            order_id = invoice_data.get('payload', '')
            
            logger.info(f"Processing invoice_expired: invoice_id={invoice_id}")
            
            # Ищем заказ
            order = None
            
            if order_id:
                order = self.db.get_order(order_id)
            
            if not order:
                order = self.db.get_order_by_invoice(str(invoice_id))
            
            if not order:
                logger.error(f"Order not found for invoice: {invoice_id}")
                return jsonify({'error': 'Order not found'}), 404
            
            # Проверяем, что заказ ещё не обработан
            if order['status'] != 'pending':
                logger.info(f"Order {order['order_id']} status is {order['status']}")
                return jsonify({'status': 'already_processed'}), 200
            
            # Обновляем статус заказа
            self.db.update_order_status(order['order_id'], 'expired')
            
            # Отправляем уведомление пользователю
            self._send_notification(order, 'expired', invoice_data)
            
            logger.info(f"Order {order['order_id']} marked as expired")
            return jsonify({'status': 'ok'}), 200
            
        except Exception as e:
            logger.error(f"Error processing invoice_expired: {e}")
            return jsonify({'error': str(e)}), 500
    
    def _send_notification(
        self, 
        order: Dict[str, Any], 
        notification_type: str,
        invoice_data: Dict[str, Any] = None
    ):
        """Отправить уведомление пользователю через Telegram API"""
        try:
            import requests
            
            from config import MESSAGES
            
            if notification_type == 'success':
                # Формируем сообщение об успешной оплате
                asset = invoice_data.get('asset', '') if invoice_data else ''
                amount = invoice_data.get('amount', '') if invoice_data else ''
                
                text = f"""
🎉 <b>Платёж успешно получен!</b>

✅ Заказ #{order['order_id']} оплачен
💰 Сумма: {amount} {asset} (${order['amount_usd']})
📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}

💡 Дополнительная информация:
• Комиссия: {invoice_data.get('fee_amount', 'N/A') if invoice_data else 'N/A'}
• Статус: Оплачен

Спасибо за покупку! 🎁
                """
            elif notification_type == 'expired':
                text = f"""
⏰ <b>Срок оплаты истёк</b>

Заказ #{order['order_id']} не был оплачен вовремя.

🔄 Хотите создать новый платёж?
                """
            else:
                text = MESSAGES['payment_failed'].format(
                    order_id=order['order_id']
                )
            
            # Отправляем через Telegram API
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            response = requests.post(url, json={
                'chat_id': order['user_id'],
                'text': text,
                'parse_mode': 'HTML'
            }, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Notification sent to user {order['user_id']}")
            else:
                logger.warning(
                    f"Failed to send notification to user {order['user_id']}: "
                    f"{response.text}"
                )
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
    
    def run(self, host: str = None, port: int = None):
        """Запустить вебхук-сервер"""
        self.app.run(
            host=host or config.webhook.listen_host,
            port=port or config.webhook.listen_port,
            debug=False,
            threaded=True
        )
    
    def run_background(self, host: str = None, port: int = None):
        """Запустить вебхук-сервер в фоновом режиме"""
        thread = Thread(
            target=self.run,
            args=(host, port),
            daemon=True
        )
        thread.start()
        return thread


def create_webhook_handler(
    db: Database, 
    cryptobot_api_token: str, 
    bot_token: str, 
    admin_ids: list
) -> CryptoBotWebhookHandler:
    """Создать обработчик вебхуков"""
    return CryptoBotWebhookHandler(
        db=db,
        cryptobot_api_token=cryptobot_api_token,
        bot_token=bot_token,
        admin_ids=admin_ids
    )


# ============ Flask приложение ============

# Глобальные переменные
webhook_handler = None


def init_webhook_app(
    db: Database, 
    cryptobot_api_token: str, 
    bot_token: str, 
    admin_ids: list
) -> Flask:
    """Инициализировать Flask приложение для вебхуков"""
    global webhook_handler
    
    webhook_handler = create_webhook_handler(
        db=db,
        cryptobot_api_token=cryptobot_api_token,
        bot_token=bot_token,
        admin_ids=admin_ids
    )
    
    return webhook_handler.app


# ============ Утилиты для вебхуков ============

def generate_webhook_url() -> str:
    """Сгенерировать URL вебхука"""
    host = config.webhook.webhook_host
    path = config.webhook.webhook_path
    return f"{host}{path}"


def register_webhook(webhook_url: str = None, secret: str = None) -> bool:
    """
    Зарегистрировать вебхук в CryptoBot
    
    Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#webhooks
    
    Args:
        webhook_url: URL для вебхука
        secret: Секретный ключ (опционально)
    
    Returns:
        bool: True если успешно
    """
    try:
        import requests
        
        url = webhook_url or generate_webhook_url()
        api_secret = secret or config.webhook_secret
        
        api_url = "https://pay.crypt.bot/api/setWebhook"
        headers = {
            'Crypto-Pay-API-Token': config.cryptobot.api_token,
            'Content-Type': 'application/json'
        }
        
        data = {
            'url': url,
        }
        
        if api_secret:
            data['secret'] = api_secret
        
        response = requests.post(api_url, json=data, headers=headers, timeout=10)
        result = response.json()
        
        if result.get('ok'):
            logger.info(f"Webhook registered: {url}")
            return True
        else:
            error_msg = result.get('error', {}).get('message', 'Unknown error')
            logger.error(f"Failed to register webhook: {error_msg}")
            return False
            
    except Exception as e:
        logger.error(f"Error registering webhook: {e}")
        return False


def delete_webhook() -> bool:
    """
    Удалить вебхук из CryptoBot
    
    Returns:
        bool: True если успешно
    """
    try:
        import requests
        
        api_url = "https://pay.crypt.bot/api/deleteWebhook"
        headers = {
            'Crypto-Pay-API-Token': config.cryptobot.api_token
        }
        
        response = requests.post(api_url, headers=headers, timeout=10)
        result = response.json()
        
        if result.get('ok'):
            logger.info("Webhook deleted")
            return True
        else:
            error_msg = result.get('error', {}).get('message', 'Unknown error')
            logger.error(f"Failed to delete webhook: {error_msg}")
            return False
            
    except Exception as e:
        logger.error(f"Error deleting webhook: {e}")
        return False


def get_webhook_info() -> Dict[str, Any]:
    """
    Получить информацию о вебхуке
    
    Returns:
        Dict с информацией о вебхуке
    """
    try:
        import requests
        
        api_url = "https://pay.crypt.bot/api/getWebhookInfo"
        headers = {
            'Crypto-Pay-API-Token': config.cryptobot.api_token
        }
        
        response = requests.get(api_url, headers=headers, timeout=10)
        result = response.json()
        
        if result.get('ok'):
            return result.get('result', {})
        else:
            return {}
            
    except Exception as e:
        logger.error(f"Error getting webhook info: {e}")
        return {}


def get_app_info() -> Dict[str, Any]:
    """
    Получить информацию о приложении
    
    Returns:
        Dict с информацией о приложении
    """
    try:
        import requests
        
        api_url = "https://pay.crypt.bot/api/getMe"
        headers = {
            'Crypto-Pay-API-Token': config.cryptobot.api_token
        }
        
        response = requests.get(api_url, headers=headers, timeout=10)
        result = response.json()
        
        if result.get('ok'):
            return result.get('result', {})
        else:
            return {}
            
    except Exception as e:
        logger.error(f"Error getting app info: {e}")
        return {}
