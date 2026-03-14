"""
Utility functions for the trading bot.
- Balance queries
- Logging helpers
- Ticker name mapping
"""
import logging
from datetime import datetime


# ── 종목명 매핑 ────────────────────────────────────────────────────────────
TICKER_NAMES = {
    # 업비트 (코인)
    "KRW-BTC":  "비트코인",
    "KRW-ETH":  "이더리움",
    "KRW-XRP":  "리플",
    "KRW-SOL":  "솔라나",
    "KRW-ADA":  "에이다",
    "KRW-DOGE": "도지코인",
    # 한국투자증권 (주식)
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "035420": "NAVER",
    "068270": "셀트리온",
}


def get_ticker_display(ticker: str) -> str:
    """종목코드 + 종목명 형태로 반환. 예: '005930 삼성전자', 'KRW-BTC 비트코인'"""
    name = TICKER_NAMES.get(ticker, "")
    return f"{ticker} {name}" if name else ticker


def is_stock(ticker: str) -> bool:
    """주식 종목인지 여부 (KRW-로 시작하지 않으면 주식)"""
    return not ticker.startswith("KRW-")


def setup_logger(log_file="trade.log"):
    """Set up file and console logging."""
    logger = logging.getLogger("trading_bot")
    logger.setLevel(logging.INFO)

    # File handler
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger


def get_coin_balance(upbit, ticker):
    """Get coin balance for a specific ticker (e.g. 'KRW-BTC' -> BTC amount)."""
    balances = upbit.get_balances()
    currency = ticker.split('-')[1]
    for b in balances:
        if b['currency'] == currency:
            if b['balance'] is not None:
                return float(b['balance'])
            else:
                return 0
    return 0


def get_krw_balance(upbit):
    """Get available KRW balance."""
    return upbit.get_balance("KRW")


def format_price(price):
    """Format price with comma separator."""
    return f"{price:,.0f}"
