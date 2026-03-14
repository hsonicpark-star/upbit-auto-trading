"""
Trading Strategy Module
- Moving Average (MA) Strategy only (pyupbit)
- Supports day / 4-hour (minute240) intervals

Caching strategy:
  - OHLCV + MA lines : 300s (chart data - only changes when new candle forms)
  - Current price    :  10s (lightweight ticker call)
  - MA signal values :  60s (MA values derived from OHLCV - stable between candles)
"""
import streamlit as st
import pandas as pd

# Interval display name map
INTERVAL_MAP = {
    "일봉 (1D)":    "day",
    "4시간봉 (4H)": "minute240",
}


def get_start_time(_broker, ticker):
    """Get daily candle start time (Upbit resets at 09:00 KST, KIS at 00:00 KST)."""
    df = _broker.get_ohlcv(ticker, interval="day", count=1)
    if df is not None and not df.empty:
        return df.index[0]
    return None


@st.cache_data(ttl=300)   # Chart OHLCV: candle data changes at most once per candle period
def get_ohlcv_with_ma(_broker, ticker, ma_periods_tuple, display_count=90, interval="day"):
    """Fetch OHLCV + compute MA lines. ma_periods_tuple must be a tuple (hashable).

    Fetches display_count + max(ma_periods) candles for warm-up so every
    displayed row has a valid MA value (no leading NaN).
    """
    ma_periods = list(ma_periods_tuple)
    max_period = max(ma_periods)
    fetch_count = display_count + max_period

    df = _broker.get_ohlcv(ticker, interval=interval, count=fetch_count)
    if df is None or df.empty:
        return pd.DataFrame()
    for p in ma_periods:
        df[f"MA{p}"] = df['close'].rolling(window=p).mean()

    # 실시간 모니터링을 위해 마지막(현재 진행 중인) 캔들도 포함하여 리턴함
    return df.tail(display_count).copy()


@st.cache_data(ttl=60)    # MA value only (does not include current price)
def get_ma_value(_broker, ticker, ma_period=20, interval="day"):
    """Compute MA value for the given period. Stable between candle periods.
    
    Returns only the MA value (float) - does NOT call get_current_price.
    """
    warm_up = ma_period + 5
    df = _broker.get_ohlcv(ticker, interval=interval, count=warm_up)
    if df is None or df.empty or len(df) < 2:
        return {
            "ma_value":   0.0,
            "prev_close": 0.0,
            "prev_ma":    0.0,
        }
    df['ma'] = df['close'].rolling(window=ma_period).mean()

    # Use the last COMPLETED candle (iloc[-2]) as MA basis.
    # iloc[-1] is the current open (unfinished) candle - excluded.
    ma_value   = float(df['ma'].iloc[-2])
    prev_close = float(df['close'].iloc[-3])   # candle before last completed
    prev_ma    = float(df['ma'].iloc[-3])

    return {
        "ma_value":   ma_value,
        "prev_close": prev_close,
        "prev_ma":    prev_ma,
    }


@st.cache_data(ttl=1)  # KIS는 REST 콜, 업비트는 모듈캐시지만 속도를 위해 1초
def get_current_price_cached(_broker, ticker):
    """Fetch current price with a short cache TTL."""
    return _broker.get_current_price(ticker)


def check_ma_signal(_broker, ticker, ma_period=20, interval="day"):
    """Build full signal dict by combining cached MA values + fresh current price.

    MA calculation (expensive OHLCV fetch) is cached 60 s.
    Current price is cached only 10 s for near-real-time display.
    """
    ma_data = get_ma_value(_broker, ticker, ma_period, interval)
    current_price = get_current_price_cached(_broker, ticker)

    ma_value   = ma_data["ma_value"]
    prev_close = ma_data["prev_close"]
    prev_ma    = ma_data["prev_ma"]

    above_ma   = current_price > ma_value
    cross_up   = (prev_close <= prev_ma) and (current_price > ma_value)
    cross_down = (prev_close >= prev_ma) and (current_price < ma_value)

    if cross_up:
        signal_label = "🔥 골든크로스 (매수)"
    elif cross_down:
        signal_label = "❄️ 데드크로스 (매도)"
    elif above_ma:
        signal_label = "🟢 이평선 위 (홀드)"
    else:
        signal_label = "🔴 이평선 아래 (관망)"

    return {
        "current_price": current_price,
        "ma_value":      ma_value,
        "above_ma":      above_ma,
        "cross_up":      cross_up,
        "cross_down":    cross_down,
        "buy_signal":    cross_up or above_ma,
        "signal_label":  signal_label,
        "diff":          current_price - ma_value,
        "diff_pct":      ((current_price - ma_value) / ma_value * 100) if ma_value > 0 else 0.0,
    }
