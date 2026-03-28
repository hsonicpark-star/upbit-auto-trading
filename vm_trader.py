"""
VM Auto Trader – GitHub Actions / Manual 실행 진입점

실행 방법:
  python vm_trader.py --mode auto           # 자동매매 (GitHub Actions 호출)
  python vm_trader.py --mode manual --side buy  --ticker KRW-BTC --amount 10000
  python vm_trader.py --mode manual --side sell --ticker KRW-BTC --amount 0.0001

환경변수:
  DRY_RUN=true   → 실제 주문 건너뜀 (로그만)
  UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY → 업비트 API 키
"""

import os
import sys
import json
import argparse
import logging
import pyupbit
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from broker_upbit import BrokerUpbit

# ─── 설정 ──────────────────────────────────────────────────────────────────
load_dotenv()

DRY_RUN       = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")
TICKER        = "KRW-BTC"
DONCHIAN_HIGH = 115          # 4H 상단 기간
DONCHIAN_LOW  = 105          # 4H 하단 기간
SMA_PERIOD    = 29           # 1D SMA 기간
DATA_DIR      = Path(__file__).parent / "data"
KST           = timezone(timedelta(hours=9))

BALANCE_CACHE_PATH = DATA_DIR / "balance_cache.json"
SIGNAL_STATE_PATH  = DATA_DIR / "signal_state.json"
TRADE_LOG_PATH     = DATA_DIR / "trade_log.json"

# ─── 로거 ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("vm_trader")


# ─── 유틸 ──────────────────────────────────────────────────────────────────
def now_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)


def load_json(path: Path) -> dict | list:
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def append_trade_log(entry: dict):
    logs = load_json(TRADE_LOG_PATH)
    if not isinstance(logs, list):
        logs = []
    logs.insert(0, entry)          # 최신이 맨 위
    logs = logs[:500]              # 최대 500건 유지
    save_json(TRADE_LOG_PATH, logs)


# ─── 전략 계산 ──────────────────────────────────────────────────────────────
def calc_donchian(broker: BrokerUpbit, ticker: str):
    """4H 캔들로 Donchian 채널 계산"""
    fetch = max(DONCHIAN_HIGH, DONCHIAN_LOW) + 5
    df = broker.get_ohlcv(ticker, interval="minute240", count=fetch)
    if df is None or df.empty:
        return None, None
    upper = float(df["high"].rolling(DONCHIAN_HIGH).max().iloc[-2])
    lower = float(df["low"].rolling(DONCHIAN_LOW).min().iloc[-2])
    return upper, lower


def calc_sma(broker: BrokerUpbit, ticker: str) -> float | None:
    """1D 캔들로 SMA 계산"""
    fetch = SMA_PERIOD + 5
    df = broker.get_ohlcv(ticker, interval="day", count=fetch)
    if df is None or df.empty:
        return None
    sma = float(df["close"].rolling(SMA_PERIOD).mean().iloc[-2])
    return sma


def get_signal(broker: BrokerUpbit, ticker: str) -> dict:
    """현재 가격과 전략 지표를 종합해 신호 반환"""
    current_price = pyupbit.get_current_price(ticker)
    donchian_upper, donchian_lower = calc_donchian(broker, ticker)
    sma = calc_sma(broker, ticker)

    if None in (current_price, donchian_upper, donchian_lower, sma):
        return {"signal": "ERROR", "reason": "지표 계산 실패"}

    above_upper = current_price > donchian_upper
    below_lower = current_price < donchian_lower
    above_sma   = current_price > sma

    if above_upper and above_sma:
        signal = "BUY"
        reason = f"가격({current_price:,.0f}) > Donchian상단({donchian_upper:,.0f}) AND SMA{SMA_PERIOD}({sma:,.0f})"
    elif below_lower or not above_sma:
        signal = "SELL"
        reason = (
            f"가격({current_price:,.0f}) < Donchian하단({donchian_lower:,.0f}) 또는 SMA{SMA_PERIOD}({sma:,.0f}) 하회"
        )
    else:
        signal = "HOLD"
        reason = f"가격({current_price:,.0f}) | Donchian범위내 | SMA{SMA_PERIOD}({sma:,.0f}) 위"

    return {
        "ticker":          ticker,
        "signal":          signal,
        "reason":          reason,
        "current_price":   current_price,
        "donchian_upper":  donchian_upper,
        "donchian_lower":  donchian_lower,
        "sma":             sma,
        "updated_at":      now_kst(),
    }


# ─── 주문 실행 ──────────────────────────────────────────────────────────────
def execute_buy(broker: BrokerUpbit, ticker: str) -> dict:
    """KRW 잔고의 99% 시장가 매수"""
    balances   = broker.get_balances()
    krw_entry  = next((b for b in balances if b.get("currency") == "KRW"), None)
    krw        = float(krw_entry["balance"]) if krw_entry else 0.0
    amount     = krw * 0.9995

    if amount < 5000:
        return {"status": "SKIP", "reason": f"KRW 잔고 부족 ({krw:,.0f}원)"}

    if DRY_RUN:
        logger.info(f"[DRY RUN] 매수 건너뜀 | {ticker} | {amount:,.0f}원")
        return {"status": "DRY_RUN", "ticker": ticker, "amount": amount}

    try:
        result = broker.buy_market_order(ticker, amount)
        logger.info(f"매수 완료 | {ticker} | {amount:,.0f}원 | {result}")
        return {"status": "OK", "ticker": ticker, "amount": amount, "result": str(result)}
    except Exception as e:
        logger.error(f"매수 실패: {e}")
        return {"status": "ERROR", "reason": str(e)}


def execute_sell(broker: BrokerUpbit, ticker: str) -> dict:
    """코인 잔고 전체 시장가 매도"""
    currency = ticker.split("-")[1]
    balances = broker.get_balances()
    coin     = next((b for b in balances if b.get("currency") == currency), None)
    volume   = float(coin["balance"]) if coin else 0.0

    if volume <= 0:
        return {"status": "SKIP", "reason": f"{currency} 잔고 없음"}

    if DRY_RUN:
        logger.info(f"[DRY RUN] 매도 건너뜀 | {ticker} | {volume:.8f}")
        return {"status": "DRY_RUN", "ticker": ticker, "volume": volume}

    try:
        result = broker.sell_market_order(ticker, volume)
        logger.info(f"매도 완료 | {ticker} | {volume:.8f} | {result}")
        return {"status": "OK", "ticker": ticker, "volume": volume, "result": str(result)}
    except Exception as e:
        logger.error(f"매도 실패: {e}")
        return {"status": "ERROR", "reason": str(e)}


# ─── 잔고 저장 ──────────────────────────────────────────────────────────────
def save_balance(broker: BrokerUpbit):
    try:
        balances = broker.get_balances()
        save_json(BALANCE_CACHE_PATH, {
            "updated_at": now_kst(),
            "dry_run":    DRY_RUN,
            "balances":   balances,
        })
        logger.info("잔고 캐시 저장 완료")
    except Exception as e:
        logger.error(f"잔고 저장 실패: {e}")


# ─── 자동매매 메인 ─────────────────────────────────────────────────────────
def run_auto_trade():
    logger.info(f"=== run_auto_trade | DRY_RUN={DRY_RUN} ===")
    access = os.getenv("UPBIT_ACCESS_KEY")
    secret = os.getenv("UPBIT_SECRET_KEY")
    broker = BrokerUpbit(access, secret)

    ensure_data_dir()
    save_balance(broker)

    # 신호 계산
    new_state = get_signal(broker, TICKER)
    logger.info(f"신호: {new_state['signal']} | {new_state.get('reason', '')}")

    if new_state["signal"] == "ERROR":
        entry = {
            "ts":     now_kst(),
            "type":   "ERROR",
            "ticker": TICKER,
            "detail": new_state.get("reason", ""),
        }
        append_trade_log(entry)
        save_json(SIGNAL_STATE_PATH, new_state)
        sys.exit(1)

    # 이전 신호와 비교 – 전환 시에만 주문
    prev_state = load_json(SIGNAL_STATE_PATH)
    prev_signal = prev_state.get("signal", "")
    new_signal  = new_state["signal"]

    order_result = None
    if new_signal == "BUY" and prev_signal != "BUY":
        logger.info("👉 매수 신호 전환 감지 → 매수 실행")
        order_result = execute_buy(broker, TICKER)
    elif new_signal == "SELL" and prev_signal not in ("SELL", ""):
        logger.info("👉 매도 신호 전환 감지 → 매도 실행")
        order_result = execute_sell(broker, TICKER)
    else:
        logger.info(f"신호 유지 ({prev_signal} → {new_signal}) | 주문 없음")

    # 상태 저장
    save_json(SIGNAL_STATE_PATH, new_state)

    # 거래 로그 기록
    if order_result:
        entry = {
            "ts":           now_kst(),
            "type":         "ORDER",
            "ticker":       TICKER,
            "signal":       new_signal,
            "prev_signal":  prev_signal,
            "order":        order_result,
            "price":        new_state.get("current_price"),
        }
        append_trade_log(entry)

    # 실행 기록 (주문 없어도 기록)
    run_entry = {
        "ts":      now_kst(),
        "type":    "RUN",
        "signal":  new_signal,
        "price":   new_state.get("current_price"),
        "dry_run": DRY_RUN,
    }
    append_trade_log(run_entry)

    logger.info("=== run_auto_trade 완료 ===")


# ─── 수동 주문 ──────────────────────────────────────────────────────────────
def run_manual_order(side: str, ticker: str, amount: float):
    logger.info(f"=== run_manual_order | side={side} ticker={ticker} amount={amount} DRY_RUN={DRY_RUN} ===")
    access = os.getenv("UPBIT_ACCESS_KEY")
    secret = os.getenv("UPBIT_SECRET_KEY")
    broker = BrokerUpbit(access, secret)

    ensure_data_dir()
    save_balance(broker)

    if side == "buy":
        if amount and amount > 0:
            # 금액 지정 매수
            if DRY_RUN:
                result = {"status": "DRY_RUN", "ticker": ticker, "amount": amount}
                logger.info(f"[DRY RUN] 수동 매수 건너뜀 | {ticker} | {amount:,.0f}원")
            else:
                try:
                    r = broker.buy_market_order(ticker, amount)
                    result = {"status": "OK", "ticker": ticker, "amount": amount, "result": str(r)}
                except Exception as e:
                    result = {"status": "ERROR", "reason": str(e)}
        else:
            result = execute_buy(broker, ticker)          # 전액 매수
    elif side == "sell":
        if amount and amount > 0:
            # 수량 지정 매도
            if DRY_RUN:
                result = {"status": "DRY_RUN", "ticker": ticker, "volume": amount}
                logger.info(f"[DRY RUN] 수동 매도 건너뜀 | {ticker} | {amount}")
            else:
                try:
                    r = broker.sell_market_order(ticker, amount)
                    result = {"status": "OK", "ticker": ticker, "volume": amount, "result": str(r)}
                except Exception as e:
                    result = {"status": "ERROR", "reason": str(e)}
        else:
            result = execute_sell(broker, ticker)         # 전량 매도
    else:
        logger.error(f"알 수 없는 side: {side}")
        sys.exit(1)

    entry = {
        "ts":     now_kst(),
        "type":   "MANUAL",
        "ticker": ticker,
        "side":   side,
        "amount": amount,
        "order":  result,
    }
    append_trade_log(entry)
    logger.info(f"수동 주문 결과: {result}")


# ─── CLI 진입점 ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VM Auto Trader")
    parser.add_argument("--mode",   choices=["auto", "manual"], required=True)
    parser.add_argument("--side",   choices=["buy", "sell"],    help="manual 모드 필수")
    parser.add_argument("--ticker", default=TICKER,             help=f"대상 티커 (기본: {TICKER})")
    parser.add_argument("--amount", type=float, default=0,      help="매수금액(KRW) 또는 매도수량(코인), 0=전액/전량")
    args = parser.parse_args()

    if args.mode == "auto":
        run_auto_trade()
    elif args.mode == "manual":
        if not args.side:
            parser.error("--mode manual 사용 시 --side 필수")
        run_manual_order(args.side, args.ticker, args.amount)
