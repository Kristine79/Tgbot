"""
Модуль для работы с CryptoBot API
Создание счетов, проверка статуса платежей, вывод средств
Обновлено согласно официальной документации: https://help.send.tg/en/articles/10279948-crypto-pay-api
"""

import aiohttp
import asyncio
import json
import hashlib
import hmac
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum


class CryptoBotError(Exception):
    """Исключение для ошибок CryptoBot"""
    def __init__(self, message: str, code: int = None, response: Dict = None):
        self.message = message
        self.code = code
        self.response = response
        super().__init__(self.message)


class PaymentStatus(Enum):
    """Статусы платежей"""
    PENDING = "active"    # Счёт активен, ожидает оплаты
    PAID = "paid"         # Счёт оплачен
    EXPIRED = "expired"   # Счёт истёк
    # cancelled не используется в новом API


class CurrencyType(Enum):
    """Тип валюты"""
    CRYPTO = "crypto"
    FIAT = "fiat"


@dataclass
class Invoice:
    """
    Структура счёта CryptoBot
    Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#invoice
    """
    invoice_id: int
    status: str
    currency_type: str          # 'crypto' или 'fiat'
    amount: str                 # Сумма счёта
    asset: Optional[str] = None # Криптовалюта (если currency_type='crypto')
    fiat: Optional[str] = None  # Фиат (если currency_type='fiat')
    paid_asset: Optional[str] = None
    paid_amount: Optional[str] = None
    paid_fiat_rate: Optional[str] = None
    accepted_assets: Optional[str] = None
    fee_asset: Optional[str] = None
    fee_amount: Optional[float] = None
    bot_invoice_url: str = ""   # Основной URL для оплаты
    mini_app_invoice_url: Optional[str] = None
    web_app_invoice_url: Optional[str] = None
    description: str = ""
    created_at: str = ""
    expiration_date: Optional[str] = None
    paid_usd_rate: Optional[str] = None  # Цена актива в USD (новое поле)
    allow_comments: bool = True
    allow_anonymous: bool = True
    paid_at: Optional[str] = None
    paid_anonymously: bool = False
    comment: Optional[str] = None
    hidden_message: Optional[str] = None
    payload: Optional[str] = None
    paid_btn_name: Optional[str] = None
    paid_btn_url: Optional[str] = None
    # Поля для свопов (API 1.5.1)
    swap_to: Optional[str] = None
    is_swapped: Optional[bool] = None
    swapped_uid: Optional[str] = None
    swapped_to: Optional[str] = None
    swapped_rate: Optional[str] = None
    swapped_output: Optional[str] = None
    swapped_usd_amount: Optional[str] = None
    swapped_usd_rate: Optional[str] = None
    
    # Deprecated поля (сохраняем для обратной совместимости)
    pay_url: str = ""           # Deprecated, используйте bot_invoice_url
    network: str = ""           # Deprecated, информация о сети в ответе отсутствует
    usd_rate: str = ""          # Deprecated, используйте paid_usd_rate
    fee: str = ""               # Deprecated, используйте fee_amount
    hash: str = ""              # Хеш счёта
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в словарь"""
        return {
            'invoice_id': self.invoice_id,
            'status': self.status,
            'currency_type': self.currency_type,
            'amount': self.amount,
            'asset': self.asset,
            'fiat': self.fiat,
            'bot_invoice_url': self.bot_invoice_url,
            'mini_app_invoice_url': self.mini_app_invoice_url,
            'web_app_invoice_url': self.web_app_invoice_url,
            'description': self.description,
            'created_at': self.created_at,
            'expiration_date': self.expiration_date,
            'paid_usd_rate': self.paid_usd_rate,
            'fee_amount': self.fee_amount,
            'payload': self.payload,
            # Дополнительные поля
            'paid_asset': self.paid_asset,
            'paid_amount': self.paid_amount,
            'paid_fiat_rate': self.paid_fiat_rate,
            'accepted_assets': self.accepted_assets,
            'fee_asset': self.fee_asset,
            'allow_comments': self.allow_comments,
            'allow_anonymous': self.allow_anonymous,
            'paid_at': self.paid_at,
            'paid_anonymously': self.paid_anonymously,
            'comment': self.comment,
            'hidden_message': self.hidden_message,
            'paid_btn_name': self.paid_btn_name,
            'paid_btn_url': self.paid_btn_url,
            # Поля для свопов
            'swap_to': self.swap_to,
            'is_swapped': self.is_swapped,
            'swapped_uid': self.swapped_uid,
            'swapped_to': self.swapped_to,
            'swapped_rate': self.swapped_rate,
            'swapped_output': self.swapped_output,
            'swapped_usd_amount': self.swapped_usd_amount,
            'swapped_usd_rate': self.swapped_usd_rate,
        }
    
    @property
    def is_crypto(self) -> bool:
        """Проверить, является ли счёт криптовалютным"""
        return self.currency_type == CurrencyType.CRYPTO.value
    
    @property
    def is_fiat(self) -> bool:
        """Проверить, является ли счёт фиатным"""
        return self.currency_type == CurrencyType.FIAT.value
    
    @property
    def is_paid(self) -> bool:
        """Проверить, оплачен ли счёт"""
        return self.status == PaymentStatus.PAID.value


@dataclass
class Transfer:
    """
    Структура перевода
    Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#transfer
    """
    transfer_id: int
    spend_id: str
    user_id: str
    asset: str
    amount: str
    status: str
    completed_at: str
    comment: Optional[str] = None


@dataclass
class Check:
    """
    Структура чека
    Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#check
    """
    check_id: int
    hash: str
    asset: str
    amount: str
    bot_check_url: str
    status: str
    created_at: str
    activated_at: Optional[str] = None


@dataclass
class Balance:
    """
    Структура баланса
    Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#balance
    """
    currency_code: str
    available: str
    onhold: str = "0"


@dataclass
class ExchangeRate:
    """
    Структура курса валюты
    Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#exchangerate
    """
    is_valid: bool
    is_crypto: bool
    is_fiat: bool
    source: str
    target: str
    rate: str


@dataclass
class AppStats:
    """
    Структура статистики приложения
    Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#appstats
    """
    volume: float
    conversion: float
    unique_users_count: int
    created_invoice_count: int
    paid_invoice_count: int
    start_at: str
    end_at: str


@dataclass
class PaymentCheck:
    """Результат проверки платежа"""
    invoice_id: int
    status: PaymentStatus
    amount: float
    asset: str
    is_paid: bool
    raw_response: Dict[str, Any]
    
    @property
    def amount_crypto(self) -> float:
        """Сумма в криптовалюте"""
        try:
            return float(self.amount)
        except (ValueError, TypeError):
            return 0.0


class CryptoBotAPI:
    """
    Класс для работы с CryptoBot API
    Base URL: https://pay.crypt.bot/api
    Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api
    """
    
    BASE_URL = "https://pay.crypt.bot/api"
    TESTNET_URL = "https://testnet-pay.crypt.bot/api"
    
    def __init__(self, api_token: str, app_id: str = None, use_testnet: bool = False):
        self.api_token = api_token
        self.app_id = app_id
        self.use_testnet = use_testnet
        self.session = None
    
    @property
    def base_url(self) -> str:
        """Получить базовый URL"""
        return self.TESTNET_URL if self.use_testnet else self.BASE_URL
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Получить сессию aiohttp"""
        if self.session is None or self.session.closed:
            headers = {
                'Crypto-Pay-API-Token': self.api_token,
                'Content-Type': 'application/json'
            }
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                headers=headers,
                timeout=timeout
            )
        return self.session
    
    async def _make_request(self, method: str, endpoint: str, 
                           data: Dict = None) -> Dict[str, Any]:
        """Выполнить запрос к API"""
        session = await self._get_session()
        url = f"{self.base_url}/{endpoint}"
        
        try:
            if method.upper() == 'GET':
                async with session.get(url, params=data) as response:
                    result = await response.json()
            else:
                async with session.post(url, json=data) as response:
                    result = await response.json()
            
            # Проверка на ошибки
            if result.get('ok') is True and 'result' in result:
                return result['result']
            
            error = result.get('error', {})
            raise CryptoBotError(
                message=error.get('message', 'Unknown error'),
                code=error.get('code'),
                response=result
            )
            
        except aiohttp.ClientError as e:
            raise CryptoBotError(f"Network error: {str(e)}")
    
    async def close(self):
        """Закрыть сессию"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    # ============ API методы ============
    
    async def get_me(self) -> Dict[str, Any]:
        """
        Получить информацию о приложении
        Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#getme
        """
        return await self._make_request('GET', 'getMe')
    
    async def create_invoice(
        self,
        amount: float,
        asset: str = None,
        currency_type: str = "crypto",
        fiat: str = None,
        accepted_assets: str = None,
        description: str = "Payment",
        hidden_message: str = None,
        paid_btn_name: str = None,
        paid_btn_url: str = None,
        payload: str = None,
        allow_comments: bool = True,
        allow_anonymous: bool = True,
        expires_in: int = 3600,
        swap_to: str = None,
    ) -> Invoice:
        """
        Создать счёт на оплату
        Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#createinvoice
        
        Args:
            amount: Сумма счёта (в криптовалюте или фиате)
            asset: Код криптовалюты (обязательно если currency_type='crypto')
                   Поддерживаются: USDT, TON, BTC, ETH, LTC, BNB, TRX, USDC
            currency_type: 'crypto' или 'fiat', по умолчанию 'crypto'
            fiat: Код фиатной валюты (обязательно если currency_type='fiat')
                  Поддерживаются: USD, EUR, RUB, BYN, UAH, GBP, CNY, KZT, UZS, GEL, TRY и др.
            accepted_assets: Список криптовалют для оплаты (через запятую), только для fiat
            description: Описание счёта (до 1024 символов)
            hidden_message: Сообщение после оплаты (до 2048 символов)
            paid_btn_name: Кнопка после оплаты: viewItem, openChannel, openBot, callback
            paid_btn_url: URL для кнопки
            payload: Данные для привязки к счёту (до 4KB)
            allow_comments: Разрешить комментарии, по умолчанию True
            allow_anonymous: Разрешить анонимную оплату, по умолчанию True
            expires_in: Время жизни в секундах (1-2678400), по умолчанию 3600
            swap_to: Актив для автоматического свопа после оплаты
        
        Returns:
            Invoice: Объект счёта
        """
        data = {
            'amount': str(amount),
            'currency_type': currency_type,
            'expires_in': expires_in
        }
        
        # Добавляем параметры в зависимости от типа валюты
        if currency_type == CurrencyType.CRYPTO.value:
            if not asset:
                raise CryptoBotError("Asset is required for crypto invoices")
            data['asset'] = asset
        else:
            if not fiat:
                raise CryptoBotError("Fiat currency is required for fiat invoices")
            data['fiat'] = fiat
            if accepted_assets:
                data['accepted_assets'] = accepted_assets
        
        # Добавляем остальные опциональные параметры
        if description:
            data['description'] = description[:1024]
        
        if hidden_message:
            data['hidden_message'] = hidden_message[:2048]
        
        if paid_btn_name and paid_btn_url:
            data['paid_btn_name'] = paid_btn_name
            data['paid_btn_url'] = paid_btn_url
        
        if payload:
            data['payload'] = payload
        
        if not allow_comments:
            data['allow_comments'] = False
        
        if not allow_anonymous:
            data['allow_anonymous'] = False
        
        if swap_to:
            data['swap_to'] = swap_to
        
        result = await self._make_request('POST', 'createInvoice', data)
        
        return self._parse_invoice(result)
    
    def _parse_invoice(self, data: Dict[str, Any]) -> Invoice:
        """Парсинг ответа счёта"""
        return Invoice(
            invoice_id=data['invoice_id'],
            status=data['status'],
            currency_type=data.get('currency_type', 'crypto'),
            amount=data['amount'],
            asset=data.get('asset'),
            fiat=data.get('fiat'),
            paid_asset=data.get('paid_asset'),
            paid_amount=data.get('paid_amount'),
            paid_fiat_rate=data.get('paid_fiat_rate'),
            accepted_assets=data.get('accepted_assets'),
            fee_asset=data.get('fee_asset'),
            fee_amount=data.get('fee_amount'),
            # Используем новые URL, с fallback на старые для совместимости
            bot_invoice_url=data.get('bot_invoice_url', data.get('pay_url', '')),
            mini_app_invoice_url=data.get('mini_app_invoice_url'),
            web_app_invoice_url=data.get('web_app_invoice_url'),
            description=data.get('description', ''),
            created_at=data.get('created_at', ''),
            expiration_date=data.get('expiration_date'),
            # Используем новые поля курса
            paid_usd_rate=data.get('paid_usd_rate', data.get('usd_rate', '')),
            allow_comments=data.get('allow_comments', True),
            allow_anonymous=data.get('allow_anonymous', True),
            paid_at=data.get('paid_at'),
            paid_anonymously=data.get('paid_anonymously', False),
            comment=data.get('comment'),
            hidden_message=data.get('hidden_message'),
            payload=data.get('payload'),
            paid_btn_name=data.get('paid_btn_name'),
            paid_btn_url=data.get('paid_btn_url'),
            # Поля для свопов
            swap_to=data.get('swap_to'),
            is_swapped=data.get('is_swapped'),
            swapped_uid=data.get('swapped_uid'),
            swapped_to=data.get('swapped_to'),
            swapped_rate=data.get('swapped_rate'),
            swapped_output=data.get('swapped_output'),
            swapped_usd_amount=data.get('swapped_usd_amount'),
            swapped_usd_rate=data.get('swapped_usd_rate'),
            # Deprecated поля для совместимости
            pay_url=data.get('pay_url', ''),
            usd_rate=data.get('usd_rate', ''),
            hash=data.get('hash', ''),
        )
    
    async def delete_invoice(self, invoice_id: int) -> bool:
        """
        Удалить счёт
        Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#deleteinvoice
        
        Args:
            invoice_id: ID счёта для удаления
        
        Returns:
            True в случае успеха
        """
        result = await self._make_request('POST', 'deleteInvoice', {
            'invoice_id': invoice_id
        })
        return result
    
    async def get_invoices(
        self,
        asset: str = None,
        fiat: str = None,
        invoice_ids: str = None,
        status: str = None,
        offset: int = 0,
        count: int = 100  # Используем 'count' вместо 'limit'
    ) -> List[Invoice]:
        """
        Получить список счетов
        Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#getinvoices
        
        Args:
            asset: Фильтр по криптовалюте
            fiat: Фильтр по фиатной валюте
            invoice_ids: Список ID через запятую
            status: Фильтр по статусу ('active' или 'paid')
            offset: Смещение для пагинации
            count: Количество записей (1-1000), по умолчанию 100
        
        Returns:
            List[Invoice]: Список счетов
        """
        data = {
            'offset': offset,
            'count': count
        }
        
        if asset:
            data['asset'] = asset
        if fiat:
            data['fiat'] = fiat
        if invoice_ids:
            data['invoice_ids'] = invoice_ids
        if status:
            data['status'] = status
        
        result = await self._make_request('GET', 'getInvoices', data)
        
        return [self._parse_invoice(item) for item in result.get('items', [])]
    
    async def get_invoice(self, invoice_id: int) -> Optional[Invoice]:
        """
        Получить информацию о конкретном счёте
        Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#getinvoice
        
        Args:
            invoice_id: ID счёта
        
        Returns:
            Invoice или None
        """
        try:
            result = await self._make_request('GET', f'getInvoice/{invoice_id}')
            return self._parse_invoice(result)
        except CryptoBotError as e:
            if 'INVOICE_NOT_FOUND' in str(e.message):
                return None
            raise
    
    async def check_payment(self, invoice_id: int) -> PaymentCheck:
        """
        Проверить статус платежа
        
        Args:
            invoice_id: ID счёта
        
        Returns:
            PaymentCheck: Результат проверки
        """
        invoice = await self.get_invoice(invoice_id)
        
        if invoice is None:
            return PaymentCheck(
                invoice_id=invoice_id,
                status=PaymentStatus.EXPIRED,  # Счёт не найден = истёк
                amount=0,
                asset='',
                is_paid=False,
                raw_response={}
            )
        
        # Маппинг статусов
        status_map = {
            'active': PaymentStatus.PENDING,
            'paid': PaymentStatus.PAID,
            'expired': PaymentStatus.EXPIRED
        }
        
        status = status_map.get(invoice.status, PaymentStatus.EXPIRED)
        
        try:
            amount = float(invoice.amount)
        except (ValueError, TypeError):
            amount = 0.0
        
        return PaymentCheck(
            invoice_id=invoice_id,
            status=status,
            amount=amount,
            asset=invoice.asset or '',
            is_paid=status == PaymentStatus.PAID,
            raw_response=invoice.to_dict()
        )
    
    async def create_check(
        self,
        asset: str,
        amount: float,
        pin_to_user_id: int = None,
        pin_to_username: str = None
    ) -> Check:
        """
        Создать чек
        Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#createcheck
        
        Args:
            asset: Криптовалюта (USDT, TON, BTC, ETH, LTC, BNB, TRX, USDC)
            amount: Сумма чека
            pin_to_user_id: ID пользователя для привязки
            pin_to_username: Username пользователя для привязки
        
        Returns:
            Check: Объект чека
        """
        data = {
            'asset': asset,
            'amount': str(amount)
        }
        
        if pin_to_user_id:
            data['pin_to_user_id'] = pin_to_user_id
        if pin_to_username:
            data['pin_to_username'] = pin_to_username
        
        result = await self._make_request('POST', 'createCheck', data)
        
        return Check(
            check_id=result['check_id'],
            hash=result['hash'],
            asset=result['asset'],
            amount=result['amount'],
            bot_check_url=result['bot_check_url'],
            status=result['status'],
            created_at=result['created_at'],
            activated_at=result.get('activated_at')
        )
    
    async def delete_check(self, check_id: int) -> bool:
        """
        Удалить чек
        Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#deletecheck
        
        Args:
            check_id: ID чека
        
        Returns:
            True в случае успеха
        """
        result = await self._make_request('POST', 'deleteCheck', {
            'check_id': check_id
        })
        return result
    
    async def get_checks(
        self,
        asset: str = None,
        check_ids: str = None,
        status: str = None,
        offset: int = 0,
        count: int = 100
    ) -> List[Check]:
        """
        Получить список чеков
        Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#getchecks
        
        Args:
            asset: Фильтр по криптовалюте
            check_ids: Список ID через запятую
            status: Фильтр по статусу ('active' или 'activated')
            offset: Смещение
            count: Количество (1-1000)
        
        Returns:
            List[Check]: Список чеков
        """
        data = {'offset': offset, 'count': count}
        
        if asset:
            data['asset'] = asset
        if check_ids:
            data['check_ids'] = check_ids
        if status:
            data['status'] = status
        
        result = await self._make_request('GET', 'getChecks', data)
        
        return [
            Check(
                check_id=item['check_id'],
                hash=item['hash'],
                asset=item['asset'],
                amount=item['amount'],
                bot_check_url=item['bot_check_url'],
                status=item['status'],
                created_at=item['created_at'],
                activated_at=item.get('activated_at')
            )
            for item in result.get('items', [])
        ]
    
    async def transfer(
        self,
        user_id: int,
        asset: str,
        amount: float,
        spend_id: str = None,
        comment: str = None,
        disable_send_notification: bool = False
    ) -> Transfer:
        """
        Перевести средства пользователю
        Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#transfer
        
        Args:
            user_id: Telegram User ID пользователя
            asset: Криптовалюта
            amount: Сумма перевода
            spend_id: Уникальный ID для идемпотентности (до 64 символов)
            comment: Комментарий (до 1024 символов)
            disable_send_notification: Не отправлять уведомление
        
        Returns:
            Transfer: Объект перевода
        """
        import uuid
        
        data = {
            'user_id': user_id,
            'asset': asset,
            'amount': str(amount),
            'spend_id': spend_id or str(uuid.uuid4()),
            'disable_send_notification': disable_send_notification
        }
        
        if comment:
            data['comment'] = comment[:1024]
        
        result = await self._make_request('POST', 'transfer', data)
        
        return Transfer(
            transfer_id=result['transfer_id'],
            spend_id=result['spend_id'],
            user_id=str(result['user_id']),
            asset=result['asset'],
            amount=result['amount'],
            status=result['status'],
            completed_at=result['completed_at'],
            comment=result.get('comment')
        )
    
    async def get_transfers(
        self,
        asset: str = None,
        transfer_ids: str = None,
        spend_id: str = None,
        offset: int = 0,
        count: int = 100
    ) -> List[Transfer]:
        """
        Получить список переводов
        Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#gettransfers
        
        Args:
            asset: Фильтр по криптовалюте
            transfer_ids: Список ID через запятую
            spend_id: Уникальный ID перевода
            offset: Смещение
            count: Количество (1-1000)
        
        Returns:
            List[Transfer]: Список переводов
        """
        data = {'offset': offset, 'count': count}
        
        if asset:
            data['asset'] = asset
        if transfer_ids:
            data['transfer_ids'] = transfer_ids
        if spend_id:
            data['spend_id'] = spend_id
        
        result = await self._make_request('GET', 'getTransfers', data)
        
        return [
            Transfer(
                transfer_id=item['transfer_id'],
                spend_id=item['spend_id'],
                user_id=str(item['user_id']),
                asset=item['asset'],
                amount=item['amount'],
                status=item['status'],
                completed_at=item['completed_at'],
                comment=item.get('comment')
            )
            for item in result.get('items', [])
        ]
    
    async def get_balance(self) -> List[Balance]:
        """
        Получить баланс приложения
        Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#getbalance
        
        Returns:
            List[Balance]: Список балансов по активам
        """
        result = await self._make_request('GET', 'getBalance')
        
        return [
            Balance(
                currency_code=item['currency_code'],
                available=item['available'],
                onhold=item.get('onhold', '0')
            )
            for item in result.get('balance', [])
        ]
    
    async def get_exchange_rates(self) -> List[ExchangeRate]:
        """
        Получить курсы валют
        Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#getexchangerates
        
        Returns:
            List[ExchangeRate]: Список курсов
        """
        result = await self._make_request('GET', 'getExchangeRates')
        
        return [
            ExchangeRate(
                is_valid=item['is_valid'],
                is_crypto=item['is_crypto'],
                is_fiat=item['is_fiat'],
                source=item['source'],
                target=item['target'],
                rate=item['rate']
            )
            for item in result.get('rates', [])
        ]
    
    async def get_currencies(self) -> List[str]:
        """
        Получить список поддерживаемых валют
        Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#getcurrencies
        
        Returns:
            List[str]: Список кодов валют
        """
        result = await self._make_request('GET', 'getCurrencies')
        return result.get('currencies', [])
    
    async def get_app_stats(
        self,
        start_at: str = None,
        end_at: str = None
    ) -> AppStats:
        """
        Получить статистику приложения
        Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#getstats
        
        Args:
            start_at: Начальная дата в ISO 8601
            end_at: Конечная дата в ISO 8601
        
        Returns:
            AppStats: Статистика приложения
        """
        data = {}
        
        if start_at:
            data['start_at'] = start_at
        if end_at:
            data['end_at'] = end_at
        
        result = await self._make_request('GET', 'getStats', data)
        
        return AppStats(
            volume=result['volume'],
            conversion=result['conversion'],
            unique_users_count=result['unique_users_count'],
            created_invoice_count=result['created_invoice_count'],
            paid_invoice_count=result['paid_invoice_count'],
            start_at=result['start_at'],
            end_at=result['end_at']
        )


# ============ Утилиты для вебхуков ============

def verify_webhook_signature(api_token: str, body: bytes, signature: str) -> bool:
    """
    Проверить подпись вебхука
    Документация: https://help.send.tg/en/articles/10279948-crypto-pay-api#webhooks
    
    Args:
        api_token: API токен приложения
        body: Тело запроса в байтах
        signature: Значение заголовка 'crypto-pay-api-signature'
    
    Returns:
        bool: True если подпись валидна
    """
    if not signature or not body:
        return False
    
    # Вычисляем секрет как SHA256 хеш от API токена
    secret = hashlib.sha256(api_token.encode()).digest()
    
    # Вычисляем HMAC-SHA256
    expected_signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)


def parse_webhook_payload(body: bytes) -> Dict[str, Any]:
    """
    Парсить тело вебхука
    
    Args:
        body: Тело запроса в байтах
    
    Returns:
        Dict с данными вебхука
    """
    return json.loads(body.decode('utf-8'))


class WebhookUpdate:
    """
    Структура входящего вебхука
    """
    def __init__(self, data: Dict[str, Any]):
        self.update_id = data.get('update_id')
        self.update_type = data.get('update_type')  # 'invoice_paid'
        self.request_date = data.get('request_date')
        self.payload = data.get('payload')
        
        # Парсим инвойс из payload
        if self.payload:
            self.invoice = self._parse_invoice_payload(self.payload)
    
    def _parse_invoice_payload(self, data: Dict[str, Any]) -> Invoice:
        """Парсить инвойс из вебхука"""
        return Invoice(
            invoice_id=data['invoice_id'],
            status=data['status'],
            currency_type=data.get('currency_type', 'crypto'),
            amount=data['amount'],
            asset=data.get('asset'),
            fiat=data.get('fiat'),
            paid_asset=data.get('paid_asset'),
            paid_amount=data.get('paid_amount'),
            paid_fiat_rate=data.get('paid_fiat_rate'),
            accepted_assets=data.get('accepted_assets'),
            fee_asset=data.get('fee_asset'),
            fee_amount=data.get('fee_amount'),
            bot_invoice_url=data.get('bot_invoice_url', data.get('pay_url', '')),
            mini_app_invoice_url=data.get('mini_app_invoice_url'),
            web_app_invoice_url=data.get('web_app_invoice_url'),
            description=data.get('description', ''),
            created_at=data.get('created_at', ''),
            expiration_date=data.get('expiration_date'),
            paid_usd_rate=data.get('paid_usd_rate', data.get('usd_rate', '')),
            allow_comments=data.get('allow_comments', True),
            allow_anonymous=data.get('allow_anonymous', True),
            paid_at=data.get('paid_at'),
            paid_anonymously=data.get('paid_anonymously', False),
            comment=data.get('comment'),
            hidden_message=data.get('hidden_message'),
            payload=data.get('payload'),
            paid_btn_name=data.get('paid_btn_name'),
            paid_btn_url=data.get('paid_btn_url'),
            # Поля для свопов
            swap_to=data.get('swap_to'),
            is_swapped=data.get('is_swapped'),
            swapped_uid=data.get('swapped_uid'),
            swapped_to=data.get('swapped_to'),
            swapped_rate=data.get('swapped_rate'),
            swapped_output=data.get('swapped_output'),
            swapped_usd_amount=data.get('swapped_usd_amount'),
            swapped_usd_rate=data.get('swapped_usd_rate'),
            # Deprecated
            pay_url=data.get('pay_url', ''),
            usd_rate=data.get('usd_rate', ''),
            hash=data.get('hash', ''),
        )


# ============ Синхронные утилиты ============

def create_invoice_sync(
    api_token: str,
    amount: float,
    asset: str = None,
    currency_type: str = "crypto",
    fiat: str = None,
    description: str = "Payment",
    expires_in: int = 3600,
    payload: str = None,
    use_testnet: bool = False
) -> Invoice:
    """
    Создать счёт (синхронная версия)
    
    Note: Для продакшена рекомендуется использовать асинхронную версию
    """
    import requests
    
    base_url = "https://testnet-pay.crypt.bot/api" if use_testnet else "https://pay.crypt.bot/api"
    
    headers = {
        'Crypto-Pay-API-Token': api_token,
        'Content-Type': 'application/json'
    }
    
    data = {
        'amount': str(amount),
        'currency_type': currency_type,
        'expires_in': expires_in
    }
    
    if currency_type == "crypto":
        if not asset:
            raise CryptoBotError("Asset is required for crypto invoices")
        data['asset'] = asset
    else:
        if not fiat:
            raise CryptoBotError("Fiat is required for fiat invoices")
        data['fiat'] = fiat
    
    if description:
        data['description'] = description[:1024]
    if payload:
        data['payload'] = payload
    
    response = requests.post(
        f"{base_url}/createInvoice",
        json=data,
        headers=headers
    )
    
    result = response.json()
    
    if not result.get('ok'):
        raise CryptoBotError(result.get('error', {}).get('message', 'Error'))
    
    # Парсим ответ
    invoice_data = result['result']
    
    return Invoice(
        invoice_id=invoice_data['invoice_id'],
        status=invoice_data['status'],
        currency_type=invoice_data.get('currency_type', 'crypto'),
        amount=invoice_data['amount'],
        asset=invoice_data.get('asset'),
        fiat=invoice_data.get('fiat'),
        bot_invoice_url=invoice_data.get('bot_invoice_url', invoice_data.get('pay_url', '')),
        mini_app_invoice_url=invoice_data.get('mini_app_invoice_url'),
        web_app_invoice_url=invoice_data.get('web_app_invoice_url'),
        description=invoice_data.get('description', ''),
        created_at=invoice_data.get('created_at', ''),
        expiration_date=invoice_data.get('expiration_date'),
        paid_usd_rate=invoice_data.get('paid_usd_rate', invoice_data.get('usd_rate', '')),
        fee_amount=invoice_data.get('fee_amount'),
        payload=invoice_data.get('payload'),
        pay_url=invoice_data.get('pay_url', ''),
        usd_rate=invoice_data.get('usd_rate', ''),
    )


def check_payment_sync(
    api_token: str,
    invoice_id: int,
    use_testnet: bool = False
) -> PaymentCheck:
    """
    Проверить платёж (синхронная версия)
    """
    import requests
    
    base_url = "https://testnet-pay.crypt.bot/api" if use_testnet else "https://pay.crypt.bot/api"
    
    headers = {
        'Crypto-Pay-API-Token': api_token
    }
    
    try:
        response = requests.get(
            f"{base_url}/getInvoice/{invoice_id}",
            headers=headers
        )
        
        result = response.json()
        
        if not result.get('ok'):
            return PaymentCheck(
                invoice_id=invoice_id,
                status=PaymentStatus.EXPIRED,
                amount=0,
                asset='',
                is_paid=False,
                raw_response={}
            )
        
        data = result['result']
        
        status_map = {
            'active': PaymentStatus.PENDING,
            'paid': PaymentStatus.PAID,
            'expired': PaymentStatus.EXPIRED
        }
        
        status = status_map.get(data['status'], PaymentStatus.EXPIRED)
        
        try:
            amount = float(data['amount'])
        except (ValueError, TypeError):
            amount = 0.0
        
        return PaymentCheck(
            invoice_id=invoice_id,
            status=status,
            amount=amount,
            asset=data.get('asset', ''),
            is_paid=status == PaymentStatus.PAID,
            raw_response=data
        )
        
    except Exception as e:
        return PaymentCheck(
            invoice_id=invoice_id,
            status=PaymentStatus.EXPIRED,
            amount=0,
            asset='',
            is_paid=False,
            raw_response={'error': str(e)}
        )


# ============ Поддерживаемые валюты ============

SUPPORTED_CRYPTOCURRENCIES = [
    "USDT", "TON", "BTC", "ETH", "LTC", "BNB", "TRX", "USDC"
]

SUPPORTED_FIAT = [
    "USD", "EUR", "RUB", "BYN", "UAH", "GBP", "CNY", "KZT", 
    "UZS", "GEL", "TRY", "AMD", "THB", "INR", "BRL", "IDR", 
    "AZN", "AED", "PLN", "ILS"
]

SWAP_TARGETS = [
    "USDT", "TON", "TRX", "ETH", "SOL", "BTC", "LTC"
]

PAID_BUTTON_TYPES = [
    "viewItem", "openChannel", "openBot", "callback"
]
