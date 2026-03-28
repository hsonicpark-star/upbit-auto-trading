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
import csv
import json
import time
import shutil
import fcntl
import argparse
import logging
import functools
import subprocess
import requests
import pyupbit
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from broker_upbit import BrokerUpbit

# ─── 설정 ──────────────────────────────────────────────────────────────────
load_dotenv()

DRY_RUN           = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")
TELEGRAM_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID", "")
TICKER        = "KRW-BTC"
DONCHIAN_HIGH = 115          # 4H 상단 기간
DONCHIAN_LOW  = 105          # 4H 하단 기간
SMA_PERIOD    = 29           # 1D SMA 기간
DATA_DIR      = Path(__file__).parent / "data"
KST           = timezone(timedelta(hours=9))

BALANCE_CACHE_PATH   = DATA_DIR / "balance_cache.json"
SIGNAL_STATE_PATH    = DATA_DIR / "signal_state.json"
TRADE_LOG_PATH       = DATA_DIR / "trade_log.json"
TRADE_LOG_CSV_PATH   = DATA_DIR / "trade_log.csv"
RESERVE_ORDERS_PATH  = DATA_DIR / "reserve_orders.json"
BACKUP_DIR         = DATA_DIR / "backup"
LOCK_FILE_PATH     = DATA_DIR / "vm_trader.lock"

MAX_RETRIES  = 3    # API 호출 최대 재시도 횟수
RETRY_DELAY  = 5    # 재시도 대기 시간 (초)

# ─── 로거 ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("vm_trader")


# ─── 중복 실행 방지 (flock) ────────────────────────────────────────────────
class SingleInstanceLock:
    """fcntl 기반 파일 락 – 동일 프로세스가 중복 실행되면 즉시 종료."""
    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._fp = None

    def __enter__(self):
        self.lock_path.parent.mkdir(exist_ok=True)
        self._fp = open(self.lock_path, "w")
        try:
            fcntl.flock(self._fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            self._fp.close()
            raise RuntimeError("이미 실행 중인 vm_trader 인스턴스가 있습니다.")
        self._fp.write(str(os.getpid()))
        self._fp.flush()
        return self

    def __exit__(self, *_):
        if self._fp:
            fcntl.flock(self._fp, fcntl.LOCK_UN)
            self._fp.close()
            try:
                self.lock_path.unlink(missing_ok=True)
            except Exception:
                pass


# ─── 재시도 데코레이터 ─────────────────────────────────────────────────────
def with_retry(max_retries: int = MAX_RETRIES, delay: int = RETRY_DELAY):
    """네트워크/API 오류 시 최대 max_retries 회 재시도."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_err = e
                    logger.warning(f"{func.__name__} 실패 ({attempt}/{max_retries}): {e}")
                    if attempt < max_retries:
                        time.sleep(delay)
            raise last_err
        return wrapper
    return decorator


# ─── 상태 파일 백업 ────────────────────────────────────────────────────────
def backup_state():
    """signal_state / balance_cache 를 backup/ 에 타임스탬프 복사 후 7일치 유지."""
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    for src in [SIGNAL_STATE_PATH, BALANCE_CACHE_PATH]:
        if src.exists():
            try:
                shutil.copy2(src, BACKUP_DIR / f"{src.stem}_{ts}.json")
            except Exception as e:
                logger.warning(f"백업 실패 {src.name}: {e}")
    # 7일 이상 된 백업 파일 자동 삭제
    cutoff = datetime.now(KST) - timedelta(days=7)
    for f in BACKUP_DIR.glob("*.json"):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime, tz=KST) < cutoff:
                f.unlink()
        except Exception:
            pass


# ─── Telegram 알림 ─────────────────────────────────────────────────────────
def send_telegram(message: str):
    """Telegram 메시지 전송. 토큰/Chat ID 없으면 무시."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception as e:
        logger.warning(f"Telegram 전송 실패: {e}")


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
    _append_trade_csv(entry)


# CSV 컬럼 순서
_CSV_FIELDS = ["ts", "type", "ticker", "signal", "prev_signal", "price",
               "order_status", "amount", "profit_pct"]

def _append_trade_csv(entry: dict):
    """trade_log.json 항목을 CSV에도 한 줄 추가 (엑셀 분석용)."""
    order = entry.get("order", {}) or {}
    row = {
        "ts":           entry.get("ts", ""),
        "type":         entry.get("type", ""),
        "ticker":       entry.get("ticker", "KRW-BTC"),
        "signal":       entry.get("signal", ""),
        "prev_signal":  entry.get("prev_signal", ""),
        "price":        entry.get("price", ""),
        "order_status": order.get("status", ""),
        "amount":       order.get("amount", order.get("volume", "")),
        "profit_pct":   entry.get("profit_pct", ""),
    }
    write_header = not TRADE_LOG_CSV_PATH.exists()
    try:
        with open(TRADE_LOG_CSV_PATH, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        logger.warning(f"CSV 기록 실패: {e}")


# ─── 전략 계산 ──────────────────────────────────────────────────────────────
@with_retry()
def calc_donchian(broker: BrokerUpbit, ticker: str):
    """4H 캔들로 Donchian 채널 계산"""
    fetch = max(DONCHIAN_HIGH, DONCHIAN_LOW) + 5
    df = broker.get_ohlcv(ticker, interval="minute240", count=fetch)
    if df is None or df.empty:
        return None, None
    upper = float(df["high"].rolling(DONCHIAN_HIGH).max().iloc[-2])
    lower = float(df["low"].rolling(DONCHIAN_LOW).min().iloc[-2])
    return upper, lower


@with_retry()
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
    get_price = with_retry()(lambda: pyupbit.get_current_price(ticker))
    current_price = get_price()
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
    try:
        lock = SingleInstanceLock(LOCK_FILE_PATH)
        lock.__enter__()
    except RuntimeError as e:
        logger.warning(str(e))
        sys.exit(0)   # 정상 종료 (중복 실행 아님)

    try:
        _run_auto_trade_inner()
    except Exception as e:
        logger.exception(f"run_auto_trade 예외: {e}")
        send_telegram(f"🚨 <b>VM 크래시</b>\n{now_kst()}\n{e}")
        sys.exit(1)
    finally:
        lock.__exit__(None, None, None)


def _run_auto_trade_inner():
    logger.info(f"=== run_auto_trade | DRY_RUN={DRY_RUN} ===")
    access = os.getenv("UPBIT_ACCESS_KEY")
    secret = os.getenv("UPBIT_SECRET_KEY")
    broker = BrokerUpbit(access, secret)

    ensure_data_dir()
    backup_state()        # 실행 전 현재 상태 백업
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
        send_telegram(f"⚠️ <b>VM 오류</b>\n{now_kst()}\n{new_state.get('reason', '')}")
        sys.exit(1)

    # 이전 신호와 비교 – 전환 시에만 주문
    prev_state = load_json(SIGNAL_STATE_PATH)
    prev_signal = prev_state.get("signal", "")
    new_signal  = new_state["signal"]

    order_result = None
    if new_signal == "BUY" and prev_signal != "BUY":
        logger.info("👉 매수 신호 전환 감지 → 매수 실행")
        send_telegram(
            f"🟢 <b>매수 신호 전환</b>\n"
            f"{now_kst()}\n"
            f"현재가: {new_state['current_price']:,.0f}원\n"
            f"사유: {new_state.get('reason','')}"
            + (" [DRY RUN]" if DRY_RUN else "")
        )
        order_result = execute_buy(broker, TICKER)
    elif new_signal == "SELL" and prev_signal not in ("SELL", ""):
        logger.info("👉 매도 신호 전환 감지 → 매도 실행")
        send_telegram(
            f"🔴 <b>매도 신호 전환</b>\n"
            f"{now_kst()}\n"
            f"현재가: {new_state['current_price']:,.0f}원\n"
            f"사유: {new_state.get('reason','')}"
            + (" [DRY RUN]" if DRY_RUN else "")
        )
        order_result = execute_sell(broker, TICKER)
    else:
        logger.info(f"신호 유지 ({prev_signal} → {new_signal}) | 주문 없음")

    # 수익률 계산 (BTC 보유 시)
    try:
        balances = load_json(BALANCE_CACHE_PATH).get("balances", [])
        btc = next((b for b in balances if b.get("currency") == "BTC"), None)
        if btc and float(btc.get("balance", 0)) > 0:
            avg_buy  = float(btc.get("avg_buy_price", 0))
            cur      = new_state.get("current_price", 0)
            profit   = round((cur - avg_buy) / avg_buy * 100, 2) if avg_buy > 0 else None
            new_state["avg_buy_price"] = avg_buy
            new_state["holding_btc"]   = float(btc["balance"])
            new_state["profit_pct"]    = profit
        else:
            new_state["profit_pct"] = None
    except Exception:
        new_state["profit_pct"] = None

    # 상태 저장
    save_json(SIGNAL_STATE_PATH, new_state)

    # 거래 로그 기록
    if order_result:
        status = order_result.get("status", "")
        icon = "✅" if status == "OK" else ("🧪" if status == "DRY_RUN" else "❌")
        send_telegram(
            f"{icon} <b>주문 결과</b>: {new_signal}\n"
            f"{now_kst()}\n"
            f"상태: {status}"
            + (f"\n잔고부족/사유: {order_result.get('reason','')}" if status in ("SKIP","ERROR") else "")
        )
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

    git_push_data()   # GitHub 백업 (Actions 모니터링용)
    logger.info("=== _run_auto_trade_inner 완료 ===")


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


# ─── GitHub 데이터 백업 ────────────────────────────────────────────────────
def git_push_data():
    """data/*.json·csv를 GitHub에 자동 커밋 (백업 + Actions 모니터링용)."""
    repo = str(Path(__file__).parent)
    files = [
        "data/balance_cache.json", "data/signal_state.json",
        "data/trade_log.json",     "data/trade_log.csv",
    ]
    try:
        subprocess.run(["git", "add"] + files, cwd=repo, timeout=15)
        result = subprocess.run(
            ["git", "commit", "-m", f"data: auto update {now_kst()} [skip ci]"],
            cwd=repo, capture_output=True, text=True, timeout=15,
        )
        if "nothing to commit" in result.stdout:
            logger.info("git: 변경사항 없음 (push 생략)")
            return
        subprocess.run(["git", "push"], cwd=repo, timeout=30)
        logger.info("data/ GitHub 백업 완료")
    except Exception as e:
        logger.warning(f"git push 실패: {e}")


# ─── 예약주문 VM 실행 ─────────────────────────────────────────────────────
def _exec_reserve_order(broker: BrokerUpbit, order: dict) -> tuple[bool, str]:
    """단일 예약주문 실행 (VM에서만 호출)."""
    ticker      = order["ticker"]
    side        = order["side"]
    order_type  = order.get("order_type", "시장가")
    limit_price = float(order.get("limit_price") or 0)
    amount      = float(order["amount"])
    try:
        if side == "매수":
            if order_type == "지정가" and limit_price > 0:
                qty    = amount / limit_price
                result = broker.buy_limit_order(ticker, limit_price, qty)
                label  = f"지정가매수 {ticker} {limit_price:,.0f}원×{qty:.6f}"
            else:
                result = broker.buy_market_order(ticker, amount)
                label  = f"시장가매수 {ticker} {amount:,.0f}원"
        else:
            if order_type == "지정가" and limit_price > 0:
                result = broker.sell_limit_order(ticker, limit_price, amount)
                label  = f"지정가매도 {ticker} {limit_price:,.0f}원×{amount:.6f}"
            else:
                result = broker.sell_market_order(ticker, amount)
                label  = f"시장가매도 {ticker} {amount:.6f}"

        if result is None:
            return False, "주문 거부 (잔고 부족 또는 최소금액 미달)"
        uuid = result.get("uuid", "") if isinstance(result, dict) else ""
        return True, f"✅ {label}" + (f" uuid={uuid[:8]}" if uuid else "")
    except Exception as e:
        return False, f"❌ 실행 오류: {e}"


def run_reserve_check():
    """예약주문 체크 및 실행 (cron 1분 주기 호출)."""
    ensure_data_dir()
    orders = load_json(RESERVE_ORDERS_PATH)
    if not isinstance(orders, list) or not orders:
        logger.info("예약주문 체크 완료 | 등록된 주문 없음")
        return

    access = os.getenv("UPBIT_ACCESS_KEY")
    secret = os.getenv("UPBIT_SECRET_KEY")
    broker = BrokerUpbit(access, secret)

    now     = datetime.now(KST).replace(tzinfo=None)  # naive로 비교
    changed = False

    for i, order in enumerate(orders):
        if not order.get("active") or order.get("status") != "대기중":
            continue

        strategy = order.get("strategy", "")
        exec_at  = order.get("exec_at", "")

        try:
            exec_dt = datetime.strptime(exec_at, "%Y-%m-%d %H:%M")
        except ValueError:
            continue

        fired = False

        if strategy == "시간 지정 실행":
            fired = now >= exec_dt

        elif strategy == "목표가 돌파 시 매수":
            if now >= exec_dt:          # 만료 → 취소
                orders[i]["status"] = "취소"
                orders[i]["result"] = "만료 취소"
                changed = True
                logger.info(f"예약주문 #{order['id']} 만료 취소")
                continue
            target = float(order.get("target_price", 0))
            cur    = pyupbit.get_current_price(order["ticker"])
            fired  = cur is not None and cur >= target

        elif strategy == "이평선 상향 돌파 시 매수":
            if now >= exec_dt:
                # 확인 시각에 MA 체크
                ma_period = int(order.get("ma_period", 20))
                df = broker.get_ohlcv(order["ticker"], interval="day", count=ma_period + 2)
                if df is not None and not df.empty:
                    ma  = float(df["close"].rolling(ma_period).mean().iloc[-2])
                    cur = pyupbit.get_current_price(order["ticker"])
                    fired = cur is not None and cur > ma

        elif strategy == "리밸런싱 (비율)":
            fired = now >= exec_dt

        if fired:
            if DRY_RUN:
                success, msg = True, f"[DRY RUN] 스킵"
            else:
                success, msg = _exec_reserve_order(broker, order)
            orders[i]["status"] = "완료" if success else "실패"
            orders[i]["result"] = msg
            orders[i]["executed_at"] = now_kst()
            changed = True
            logger.info(f"예약주문 #{order['id']} {orders[i]['status']}: {msg}")
            send_telegram(
                f"{'✅' if success else '❌'} <b>예약주문 {orders[i]['status']}</b>\n"
                f"#{order['id']} {order['ticker']} {order['side']}\n{msg}"
            )
            append_trade_log({
                "ts":     now_kst(),
                "type":   "RESERVE",
                "ticker": order["ticker"],
                "signal": order["side"],
                "order":  {"status": "OK" if success else "ERROR", "detail": msg},
            })

    if changed:
        save_json(RESERVE_ORDERS_PATH, orders)
    logger.info(f"예약주문 체크 완료 | 총 {len(orders)}건")


# ─── CLI 진입점 ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VM Auto Trader")
    parser.add_argument("--mode",   choices=["auto", "manual", "reserve"], required=True)
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
    elif args.mode == "reserve":
        run_reserve_check()
