import sys
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List
import os
from dotenv import load_dotenv
import warnings
import requests
import asyncio

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

# ====================== НАСТРОЙКИ ======================
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('trading_bot.log', encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
warnings.filterwarnings('ignore')

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TINKOFF_TOKEN = os.getenv('TINKOFF_TOKEN')

if not TELEGRAM_TOKEN or not TINKOFF_TOKEN:
    logger.error("❌ Токены не найдены в .env!")
    sys.exit(1)

# ====================== СПИСОК АКЦИЙ ======================
TRADING_PAIRS = [
    {"ticker": "SBER", "name": "Сбербанк", "figi": "BBG004730N88", "sector": "Финансы", "moex_ticker": "SBER"},
    {"ticker": "SBERP", "name": "Сбербанк-п", "figi": "BBG0047315Y7", "sector": "Финансы", "moex_ticker": "SBERP"},
    {"ticker": "GAZP", "name": "Газпром", "figi": "BBG004730RP0", "sector": "Энергетика", "moex_ticker": "GAZP"},
    {"ticker": "LKOH", "name": "Лукойл", "figi": "BBG004731032", "sector": "Энергетика", "moex_ticker": "LKOH"},
    {"ticker": "YDEX", "name": "Яндекс", "figi": "TCS00A107RZ4", "sector": "IT", "moex_ticker": "YDEX"},
    {"ticker": "TCSG", "name": "ТКС Холдинг", "figi": "TCS00A107QM0", "sector": "Финансы", "moex_ticker": "TCSG"},
    {"ticker": "ROSN", "name": "Роснефть", "figi": "BBG004731354", "sector": "Энергетика", "moex_ticker": "ROSN"},
    {"ticker": "NVTK", "name": "Новатэк", "figi": "BBG00475J7X6", "sector": "Энергетика", "moex_ticker": "NVTK"},
    {"ticker": "TATN", "name": "Татнефть", "figi": "BBG0047315D0", "sector": "Энергетика", "moex_ticker": "TATN"},
    {"ticker": "TATNP", "name": "Татнефть-п", "figi": "BBG0047315F7", "sector": "Энергетика", "moex_ticker": "TATNP"},
    {"ticker": "GMKN", "name": "ГМК Норникель", "figi": "BBG004731489", "sector": "Металлургия", "moex_ticker": "GMKN"},
    {"ticker": "PLZL", "name": "Полюс", "figi": "BBG0047315J1", "sector": "Добыча", "moex_ticker": "PLZL"},
    {"ticker": "MGNT", "name": "Магнит", "figi": "BBG00475KKY8", "sector": "Ритейл", "moex_ticker": "MGNT"},
    {"ticker": "VTBR", "name": "ВТБ", "figi": "BBG004730JJ5", "sector": "Финансы", "moex_ticker": "VTBR"},
    {"ticker": "ALRS", "name": "АЛРОСА", "figi": "BBG0047315L6", "sector": "Добыча", "moex_ticker": "ALRS"},
    {"ticker": "MOEX", "name": "Московская биржа", "figi": "BBG004730ZJ9", "sector": "Финансы", "moex_ticker": "MOEX"},
    {"ticker": "CHMF", "name": "Северсталь", "figi": "BBG0047315G6", "sector": "Металлургия", "moex_ticker": "CHMF"},
    {"ticker": "NLMK", "name": "НЛМК", "figi": "BBG004S68JR8", "sector": "Металлургия", "moex_ticker": "NLMK"},
    {"ticker": "SNGS", "name": "Сургутнефтегаз", "figi": "BBG004731539", "sector": "Энергетика", "moex_ticker": "SNGS"},
    {"ticker": "SNGSP", "name": "Сургутнефтегаз-п", "figi": "BBG004S68C39", "sector": "Энергетика", "moex_ticker": "SNGSP"},
    {"ticker": "MTSS", "name": "МТС", "figi": "BBG004S68A65", "sector": "Телеком", "moex_ticker": "MTSS"},
    {"ticker": "IRAO", "name": "Интер РАО", "figi": "BBG004S68507", "sector": "Энергетика", "moex_ticker": "IRAO"},
    {"ticker": "AFLT", "name": "Аэрофлот", "figi": "BBG004S681W1", "sector": "Транспорт", "moex_ticker": "AFLT"},
    {"ticker": "OZON", "name": "Ozon", "figi": "BBG00Y3CQX00", "sector": "Ритейл", "moex_ticker": "OZON"},
    {"ticker": "PHOR", "name": "ФосАгро", "figi": "BBG00475JZZ6", "sector": "Химия", "moex_ticker": "PHOR"},
    {"ticker": "RUAL", "name": "РУСАЛ", "figi": "BBG008F2T3T2", "sector": "Металлургия", "moex_ticker": "RUAL"},
    {"ticker": "AFKS", "name": "АФК Система", "figi": "BBG0047315B4", "sector": "Холдинг", "moex_ticker": "AFKS"}
]

TICKER_TO_FIGI = {p["ticker"]: p["figi"] for p in TRADING_PAIRS}
TICKER_TO_MOEX = {p["ticker"]: p["moex_ticker"] for p in TRADING_PAIRS}

def format_price(price: float) -> str:
    if price < 1: return f"{price:.4f}₽"
    elif price < 10: return f"{price:.3f}₽"
    return f"{price:.2f}₽"

# ====================== RATE LIMITER ======================
class RateLimiter:
    def __init__(self, max_requests: int = 90):
        self.max_req = max_requests
        self.requests = []

    def wait_if_needed(self):
        now = time.time()
        self.requests = [req for req in self.requests if req > now - 60]
        if len(self.requests) >= self.max_req:
            wait_time = self.requests[0] + 60 - now
            if wait_time > 0: time.sleep(wait_time)
        self.requests.append(time.time())

# ====================== TINKOFF API (V3.3 — без 404) ======================
class TinkoffIndicatorsAPI:
    def __init__(self, token: str):
        self.base_url = "https://invest-public-api.tbank.ru/rest"
        self.session = requests.Session()
        self.session.headers.update({'Authorization': f'Bearer {token}'})
        self.session.verify = False
        self.limiter = RateLimiter(90)
        logger.warning("⚠️ SSL-проверка отключена (антивирус)")

    def _get_candles(self, ticker: str) -> List[Dict]:
        self.limiter.wait_if_needed()
        url = f"{self.base_url}/tinkoff.public.invest.api.contract.v1.MarketDataService/GetCandles"
        now = datetime.now(timezone.utc)
        instrument_id = f"{ticker}_TQBR"   # ← официальный рабочий формат
        payload = {
            "instrumentId": instrument_id,
            "from": (now - timedelta(days=30)).isoformat().replace('+00:00', 'Z'),
            "to": now.isoformat().replace('+00:00', 'Z'),
            "interval": "CANDLE_INTERVAL_15_MIN",
            "limit": 500
        }
        try:
            resp = self.session.post(url, json=payload, timeout=15)
            if resp.status_code != 200:
                logger.error(f"GetCandles {ticker} → {resp.status_code}")
                return []
            candles = resp.json().get("candles", [])[-300:]
            parsed = []
            for c in candles:
                close = float(c.get("close", {}).get("units", 0)) + float(c.get("close", {}).get("nano", 0)) / 1e9
                high = float(c.get("high", {}).get("units", 0)) + float(c.get("high", {}).get("nano", 0)) / 1e9
                low = float(c.get("low", {}).get("units", 0)) + float(c.get("low", {}).get("nano", 0)) / 1e9
                if close > 0:
                    parsed.append({"close": close, "high": high, "low": low})
            return parsed
        except Exception as e:
            logger.error(f"Свечи {ticker}: {e}")
            return []

    def _ema_series(self, prices: List[float], period: int) -> List[float]:
        if not prices: return []
        k = 2.0 / (period + 1)
        ema = [prices[0]]
        for p in prices[1:]:
            ema.append(p * k + ema[-1] * (1 - k))
        return ema

    def _calculate_rsi(self, closes: List[float], period: int = 14) -> float:
        if len(closes) < period + 1: return 50.0
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [max(c, 0) for c in changes]
        losses = [abs(min(c, 0)) for c in changes]
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period or 0.0001
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0: return 100.0
        rs = avg_gain / avg_loss
        return 100 - 100 / (1 + rs)

    def _calculate_macd_histogram(self, closes: List[float]) -> float:
        if len(closes) < 40: return 0.0
        ema12 = self._ema_series(closes, 12)
        ema26 = self._ema_series(closes, 26)
        macd = [f - s for f, s in zip(ema12, ema26)]
        signal = self._ema_series(macd, 9)
        return macd[-1] - signal[-1]

    def _calculate_bollinger(self, closes: List[float], period: int = 20, dev: float = 2.0) -> Dict:
        if len(closes) < period: return {'upper': 0, 'lower': 0}
        last = closes[-period:]
        middle = sum(last) / period
        std = (sum((x - middle) ** 2 for x in last) / period) ** 0.5
        return {'upper': middle + dev * std, 'lower': middle - dev * std}

    def _calculate_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        if len(highs) < period + 1: return 0.0
        trs = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1, len(highs))]
        atr = sum(trs[:period]) / period
        for tr_val in trs[period:]:
            atr = (atr * (period - 1) + tr_val) / period
        return atr

    def get_all_indicators(self, ticker: str) -> Dict:
        candles = self._get_candles(ticker)
        if len(candles) < 50:
            return {'error': True, 'rsi': 0, 'macd': {'histogram': 0}, 'bb': {'upper': 0, 'lower': 0}, 'atr': 0.0, 'ema': 0.0}
        closes = [c['close'] for c in candles]
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        return {
            'error': False,
            'rsi': self._calculate_rsi(closes),
            'macd': {'histogram': self._calculate_macd_histogram(closes)},
            'bb': self._calculate_bollinger(closes),
            'atr': self._calculate_atr(highs, lows, closes),
            'ema': self._ema_series(closes, 50)[-1]
        }

class MOEXRestAPI:
    def get_current_price(self, ticker: str) -> float:
        try:
            url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{ticker}.json"
            params = {'iss.meta': 'off', 'iss.only': 'marketdata', 'marketdata.columns': 'LAST,LCURRENTPRICE'}
            data = requests.get(url, params=params, timeout=5).json().get('marketdata', {}).get('data', [])
            if data and data[0][0]: return float(data[0][0])
            if data and data[0][1]: return float(data[0][1])
        except: pass
        return 0.0

class TradeSignalGenerator:
    def __init__(self, indicators_api):
        self.api = indicators_api

    def generate_signal(self, ticker: str, price: float, market_regime: str) -> dict:
        inds = self.api.get_all_indicators(ticker)
        rsi = inds.get('rsi')
        macd_hist = inds.get('macd', {}).get('histogram', 0)
        bb = inds.get('bb', {})
        atr = inds.get('atr')
        ema = inds.get('ema')
        reasons = []

        is_buy = rsi and rsi < 35 and price <= bb.get('lower', 0) * 1.01 and macd_hist > -0.5 and price > ema * 0.90
        is_sell = rsi and rsi > 70 and price >= bb.get('upper', 0) * 0.99 and macd_hist < 0.5 and price < ema * 1.10

        if is_buy:
            action = "BUY"
            confidence = 0.9
            reasons.append(f"🔥 Строгий BUY: RSI={rsi:.1f}, у нижней BB")
        elif is_sell:
            action = "SELL"
            confidence = 0.9
            reasons.append(f"🔥 Строгий SELL: RSI={rsi:.1f}, у верхней BB")
        else:
            action = "HOLD"
            confidence = 0.3
            reasons.append("Индикаторы в нейтральной зоне")

        sl = tp = None
        if action != "HOLD":
            vol = atr or price * 0.03
            sl = price - vol * 1.5 if action == "BUY" else price + vol * 1.5
            tp = price + vol * 3.0 if action == "BUY" else price - vol * 3.0

        return {'action': action, 'confidence': confidence, 'reasons': reasons,
                'price': price, 'stop_loss': sl, 'take_profit': tp,
                'indicators': inds, 'market_regime': market_regime}

class RealTimeEngine:
    def __init__(self):
        self.tinkoff_ind = TinkoffIndicatorsAPI(TINKOFF_TOKEN)
        self.moex = MOEXRestAPI()
        self.prices = {}
        self.generator = TradeSignalGenerator(self.tinkoff_ind)

    async def update_prices_async(self):
        for p in TRADING_PAIRS:
            price = await asyncio.to_thread(self.moex.get_current_price, p['moex_ticker'])
            if price > 0: self.prices[p['ticker']] = price
            await asyncio.sleep(0.05)

    async def calculate_market_regime(self) -> str:
        above = 0
        total = 0
        for p in TRADING_PAIRS[:10]:
            price = self.prices.get(p['ticker'], 0)
            if price > 0:
                inds = await asyncio.to_thread(self.tinkoff_ind.get_all_indicators, p['ticker'])
                if not inds.get('error') and inds['ema'] > 0:
                    total += 1
                    if price > inds['ema']: above += 1
            await asyncio.sleep(0.1)
        if total == 0: return "Боковой"
        return "Бычий" if above / total >= 0.6 else "Медвежий" if above / total <= 0.4 else "Боковой"

    def analyze(self, ticker: str, market_regime: str):
        price = self.prices.get(ticker) or self.moex.get_current_price(TICKER_TO_MOEX.get(ticker, ticker))
        if not price: return None
        return self.generator.generate_signal(ticker, price, market_regime)

# ====================== БОТ (ПОЛНОЕ МЕНЮ КАК В ОРИГИНАЛЕ) ======================
class TradingBot:
    def __init__(self):
        self.engine = RealTimeEngine()
        self.start_time = datetime.now()
        self.active_chats = set()
        self.is_monitoring = False
        self.monitor_task = None

        t_request = HTTPXRequest(connection_pool_size=8, connect_timeout=30.0)
        self.application = Application.builder().token(TELEGRAM_TOKEN).request(t_request).build()

    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.active_chats.add(update.effective_chat.id)
        await update.message.reply_text(
            "🤖 *TRADING BOT PRO (V3.3) ЗАПУЩЕН*\n\n"
            "🧠 *Интеллектуальная система:*\n"
            "• Индикаторы: RSI + MACD + Bollinger Bands\n"
            "• Фильтр тренда: EMA 50 (защита от 'падающих ножей')\n"
            "• Риск-менеджмент: ATR (Динамические стоп-лоссы)\n"
            "• Широта рынка: Оценка бычьего/медвежьего тренда\n\n"
            "📌 *Команды:*\n"
            "/analyze - Полный анализ 27 бумаг\n"
            "/signal [тикер] - Детальный анализ акции\n"
            "/prices - Показать текущие цены\n"
            "/monitor - Вкл/Выкл фоновый авто-мониторинг\n"
            "/status - Состояние системы\n"
            "/restart - Перезапуск бота",
            parse_mode="Markdown"
        )

    async def status_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        uptime = str(datetime.now() - self.start_time).split('.')[0]
        await update.message.reply_text(
            f"📊 *СТАТУС СИСТЕМЫ*\n\n"
            f"⏱ Время работы: {uptime}\n"
            f"📡 Авто-мониторинг: {'🟢 Работает' if self.is_monitoring else '🔴 Остановлен'}\n"
            f"👥 Активных чатов: {len(self.active_chats)}\n"
            f"📈 Отслеживается: {len(TRADING_PAIRS)} акций",
            parse_mode='Markdown'
        )

    async def prices_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg_obj = await update.message.reply_text("🔄 Загружаю цены голубых фишек...")
        await self.engine.update_prices_async()
        lines = [f"🔹 {p['ticker']}: {format_price(self.engine.prices.get(p['ticker'], 0))}" for p in TRADING_PAIRS]
        await msg_obj.edit_text("📈 *ТЕКУЩИЕ ЦЕНЫ*\n\n" + "\n".join(lines), parse_mode='Markdown')

    async def signal_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ Укажите тикер: `/signal SBER`", parse_mode="Markdown")
            return
        ticker = context.args[0].upper()
        if ticker not in TICKER_TO_FIGI:
            await update.message.reply_text("❌ Тикер не поддерживается.")
            return

        msg_obj = await update.message.reply_text(f"⏳ Анализирую {ticker}...")
        await self.engine.update_prices_async()
        regime = await self.engine.calculate_market_regime()
        sig = await asyncio.to_thread(self.engine.analyze, ticker, regime)

        if not sig or sig['indicators'].get('error'):
            await msg_obj.edit_text("❌ Ошибка получения данных от T-Bank. Попробуй позже.")
            return

        action_icon = "🟢 BUY" if sig['action'] == "BUY" else "🔴 SELL" if sig['action'] == "SELL" else "⚪ HOLD"
        msg = (
            f"📊 *АНАЛИЗ: {ticker}*\n\n"
            f"Текущий рынок: *{regime}*\n"
            f"Рекомендация: {action_icon}\n"
            f"Текущая цена: {format_price(sig['price'])}\n"
            f"Уверенность: {sig['confidence'] * 100}%\n\n"
        )
        if sig['action'] != 'HOLD':
            msg += f"🎯 TP: {format_price(sig['take_profit'])} | 🛑 SL: {format_price(sig['stop_loss'])}\n\n"
        msg += "📝 *Обоснование:*\n" + "\n".join([f"• {r}" for r in sig['reasons']])
        inds = sig['indicators']
        msg += f"\n\n⚙️ *Сводка данных:*\nRSI: {inds.get('rsi', 0):.1f} | EMA50: {format_price(inds.get('ema', 0))} | ATR: {format_price(inds.get('atr', 0))}"

        await msg_obj.edit_text(msg, parse_mode="Markdown")

    async def analyze_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg_obj = await update.message.reply_text("⏳ Оценка широты рынка и расчет индикаторов для 27 бумаг (~30 сек)...")
        await self.engine.update_prices_async()
        regime = await self.engine.calculate_market_regime()
        reports = []
        for p in TRADING_PAIRS:
            sig = await asyncio.to_thread(self.engine.analyze, p['ticker'], regime)
            if sig and sig['action'] != 'HOLD' and not sig['indicators'].get('error'):
                reports.append(
                    f"{'🟢 BUY' if sig['action'] == 'BUY' else '🔴 SELL'} **{p['ticker']}**\n"
                    f"Цена: {format_price(sig['price'])} | Вероятность: {sig['confidence'] * 100}%\n"
                    f"🎯 TP: {format_price(sig['take_profit'])} | 🛑 SL: {format_price(sig['stop_loss'])}\n"
                    f"💡 {sig['reasons'][0]}"
                )
            await asyncio.sleep(0.3)
        header = f"🌐 *ФОН РЫНКА:* {regime}\n\n"
        msg = header + ("\n\n".join(reports) if reports else "⚪ Строгих сигналов нет. На рынке флэт.")
        await msg_obj.edit_text(msg, parse_mode='Markdown')

    async def restart_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🔄 Перезапуск...")
        if self.is_monitoring:
            self.is_monitoring = False
            if self.monitor_task: self.monitor_task.cancel()
        self.engine = RealTimeEngine()
        await self.start_cmd(update, context)

    async def monitor_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.active_chats.add(update.effective_chat.id)
        if self.is_monitoring:
            self.is_monitoring = False
            if self.monitor_task: self.monitor_task.cancel()
            await update.message.reply_text("🛑 Мониторинг отключен.")
        else:
            self.is_monitoring = True
            self.monitor_task = asyncio.create_task(self.monitoring_loop())
            await update.message.reply_text("✅ Мониторинг включен. Бот будет искать сделки по тренду каждые 15 мин.")

    async def monitoring_loop(self):
        while self.is_monitoring:
            try:
                await self.engine.update_prices_async()
                regime = await self.engine.calculate_market_regime()
                for p in TRADING_PAIRS:
                    sig = await asyncio.to_thread(self.engine.analyze, p['ticker'], regime)
                    if sig and sig['action'] != 'HOLD' and sig['confidence'] >= 0.8 and not sig['indicators'].get('error'):
                        msg = (
                            f"🚨 *ПРОФИ СИГНАЛ* 🚨\n\n"
                            f"{'🟢 BUY' if sig['action'] == 'BUY' else '🔴 SELL'} *{p['ticker']}*\n"
                            f"Рыночный фон: {regime}\n"
                            f"Цена входа: {format_price(sig['price'])}\n"
                            f"🎯 Цель: {format_price(sig['take_profit'])} | 🛑 Стоп (по ATR): {format_price(sig['stop_loss'])}\n\n"
                            f"📝 {sig['reasons'][0]}"
                        )
                        for chat in self.active_chats:
                            await self.application.bot.send_message(chat, msg, parse_mode='Markdown')
                    await asyncio.sleep(1.0)
                await asyncio.sleep(900)
            except Exception as e:
                logger.error(f"Ошибка мониторинга: {e}")
                await asyncio.sleep(60)

    def run(self):
        self.application.add_handler(CommandHandler("start", self.start_cmd))
        self.application.add_handler(CommandHandler("analyze", self.analyze_cmd))
        self.application.add_handler(CommandHandler("monitor", self.monitor_cmd))
        self.application.add_handler(CommandHandler("prices", self.prices_cmd))
        self.application.add_handler(CommandHandler("status", self.status_cmd))
        self.application.add_handler(CommandHandler("signal", self.signal_cmd))
        self.application.add_handler(CommandHandler("restart", self.restart_cmd))

        logger.info("🚀 Бот V3.3 запущен!")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    import asyncio

    bot = TradingBot()

    # Запуск polling через updater напрямую — это решает проблему на серверах
    updater = bot.application.updater
    updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        bootstrap_retries=-1,
        timeout=30,
        read_timeout=30,
        connect_timeout=30,
        pool_timeout=30,
    )

    # Держим процесс живым (бесконечный цикл)
    updater.idle()

    # Если нужно остановить graceful (Ctrl+C)
    updater.stop()
