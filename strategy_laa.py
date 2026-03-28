"""
LAA (Lethargic Asset Allocation) 전략
--------------------------------------
Universe : SPY, IWM, GLD, BIL
Canary   : SPY > 200일 SMA → 강세장
강세장   : SPY/IWM/GLD 중 12개월 모멘텀 1위 자산 75% + BIL 25%
약세장   : BIL 100%
리밸런싱  : 월 1회 / 분기 1회 / 반기 1회 / 년 1회 선택 가능
"""

import logging
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# ── 자산 정의 ──────────────────────────────────────────────────────────────
LAA_ASSETS = {
    "SPY": {"name": "S&P 500 ETF",          "exchange_price": "AMS", "exchange_order": "AMEX"},
    "IWM": {"name": "Russell 2000 ETF",      "exchange_price": "AMS", "exchange_order": "AMEX"},
    "GLD": {"name": "Gold ETF",              "exchange_price": "AMS", "exchange_order": "AMEX"},
    "BIL": {"name": "1-3M T-Bill ETF",       "exchange_price": "AMS", "exchange_order": "AMEX"},
}

MOMENTUM_ASSETS = ["SPY", "IWM", "GLD"]   # 캐너리 OK일 때 모멘텀 비교 대상
SAFE_ASSET      = "BIL"                    # 방어 자산

# ── 리밸런싱 주기 ──────────────────────────────────────────────────────────
REBALANCE_PERIODS = {
    "월 1회":  1,
    "분기 1회": 3,
    "반기 1회": 6,
    "년 1회":  12,
}

FEE_RATE = 0.001   # 해외주식 매매 수수료 0.1% (KIS 기준 근사값)


# ── 데이터 수집 ───────────────────────────────────────────────────────────
def get_laa_prices(years_back: int = 7) -> pd.DataFrame:
    """
    yfinance로 LAA 4개 자산 종가 수집.
    200일 SMA + 252일(12개월) 모멘텀 계산을 위해 충분한 여유분 포함.
    """
    end   = datetime.now()
    start = end - timedelta(days=years_back * 365 + 400)

    frames = {}
    for symbol in LAA_ASSETS:
        try:
            df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
            if not df.empty:
                close = df["Close"]
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:, 0]
                close.index = pd.to_datetime(close.index).tz_localize(None)
                frames[symbol] = close
        except Exception as e:
            logging.warning(f"[LAA] {symbol} 데이터 수집 실패: {e}")

    if not frames:
        return pd.DataFrame()

    prices = pd.DataFrame(frames).dropna()
    return prices


# ── 신호 계산 ──────────────────────────────────────────────────────────────
def compute_laa_signal(
    prices: pd.DataFrame,
    as_of: pd.Timestamp,
    bull_momentum_pct: float = 0.75,
    bull_safe_pct: float = 0.25,
):
    """
    특정 날짜 기준 LAA 신호 계산.
    bull_momentum_pct : 강세장에서 모멘텀 1위 자산 비중 (기본 75%)
    bull_safe_pct     : 강세장에서 방어 자산(BIL) 비중 (기본 25%)
    반환: (canary_bull, momentum_dict, target_allocation_dict)
    """
    hist = prices[prices.index <= as_of]

    if len(hist) < 252:
        return None, None, {}

    current = hist.iloc[-1]

    # ① Canary: SPY > 200일 단순이동평균
    spy_200sma   = hist["SPY"].tail(200).mean()
    canary_bull  = bool(current["SPY"] > spy_200sma)

    # ② 12개월(252 거래일) 모멘텀
    past_252      = hist.iloc[-252]
    momentum      = {
        asset: round((current[asset] / past_252[asset] - 1) * 100, 2)
        for asset in MOMENTUM_ASSETS
    }

    # ③ 포트폴리오 결정
    if canary_bull:
        best_asset = max(momentum, key=momentum.get)
        target = {best_asset: bull_momentum_pct, SAFE_ASSET: bull_safe_pct}
    else:
        target = {SAFE_ASSET: 1.0}

    return canary_bull, momentum, target


# ── 리밸런싱 날짜 목록 ────────────────────────────────────────────────────
def get_rebalance_dates(start: pd.Timestamp, end: pd.Timestamp, period_months: int = 1):
    dates = []
    cur   = start + relativedelta(months=period_months)
    while cur <= end:
        dates.append(cur)
        cur += relativedelta(months=period_months)
    return dates


# ── 백테스트 ─────────────────────────────────────────────────────────────
def backtest_laa(
    period_years:      int        = 5,
    initial_capital:   float      = 10_000_000,
    period_months:     int        = 1,
    bull_momentum_pct: float      = 0.75,
    bull_safe_pct:     float      = 0.25,
    static_weights:    dict | None = None,
) -> dict | None:
    """
    LAA 전략 백테스트.
    static_weights: {"SPY": 0.25, "IWM": 0.25, ...} 형태로 전달 시
                    신호 무관하게 항상 해당 비중으로 리밸런싱 (정적 배분 모드).
    initial_capital은 USD 기준 (yfinance 데이터 자체가 USD).
    """
    prices_all = get_laa_prices(period_years + 2)
    if prices_all.empty:
        return None

    end_date   = prices_all.index[-1]
    start_date = end_date - timedelta(days=period_years * 365)
    prices_bt  = prices_all[prices_all.index >= start_date]

    if prices_bt.empty:
        return None

    rebal_dates = get_rebalance_dates(prices_bt.index[0], prices_bt.index[-1], period_months)

    # 초기화
    portfolio   = {asset: 0.0 for asset in LAA_ASSETS}
    cash        = float(initial_capital)
    prev_date   = prices_bt.index[0]
    records     = []
    trades      = []
    current_target = {}

    for date in prices_bt.index:
        cp = prices_bt.loc[date]

        # 포트폴리오 현재 가치
        port_value = cash + sum(portfolio[a] * cp[a] for a in LAA_ASSETS if a in cp.index)

        is_rebal = any(prev_date < rd <= date for rd in rebal_dates) or date == prices_bt.index[0]

        if is_rebal:
            if static_weights:
                target = static_weights
            else:
                _, _, target = compute_laa_signal(
                    prices_all[prices_all.index <= date], date,
                    bull_momentum_pct=bull_momentum_pct,
                    bull_safe_pct=bull_safe_pct,
                )
            if target:
                current_target = target

                # 과잉 보유 자산 매도 먼저
                for asset in list(portfolio.keys()):
                    if portfolio[asset] > 0 and asset not in target:
                        sell_val = portfolio[asset] * cp[asset]
                        cash    += sell_val * (1 - FEE_RATE)
                        trades.append({
                            "날짜": date, "구분": "매도", "자산": asset,
                            "수량": round(portfolio[asset], 4),
                            "가격": round(cp[asset], 2),
                            "금액": round(sell_val, 2),
                        })
                        portfolio[asset] = 0.0

                port_value = cash + sum(portfolio[a] * cp[a] for a in LAA_ASSETS if a in cp.index)

                # 매수
                for asset, weight in target.items():
                    tgt_val  = port_value * weight
                    cur_val  = portfolio.get(asset, 0) * cp.get(asset, 1)
                    diff     = tgt_val - cur_val
                    price    = cp.get(asset, 0)

                    if price > 0 and abs(diff) > 10:
                        shares = diff / price
                        if shares > 0:
                            cost              = shares * price * (1 + FEE_RATE)
                            portfolio[asset]  = portfolio.get(asset, 0) + shares
                            cash             -= cost
                            trades.append({
                                "날짜": date, "구분": "매수", "자산": asset,
                                "수량": round(shares, 4),
                                "가격": round(price, 2),
                                "금액": round(shares * price, 2),
                            })
                        elif shares < 0:
                            sell_shares      = min(abs(shares), portfolio.get(asset, 0))
                            sell_val         = sell_shares * price * (1 - FEE_RATE)
                            portfolio[asset] -= sell_shares
                            cash            += sell_val
                            trades.append({
                                "날짜": date, "구분": "매도", "자산": asset,
                                "수량": round(sell_shares, 4),
                                "가격": round(price, 2),
                                "금액": round(sell_shares * price, 2),
                            })

                port_value = cash + sum(portfolio[a] * cp[a] for a in LAA_ASSETS if a in cp.index)

        records.append({
            "date":           date,
            "portfolio_value": port_value,
            "is_rebal":       is_rebal,
        })
        prev_date = date

    records_df = pd.DataFrame(records).set_index("date")
    trades_df  = pd.DataFrame(trades) if trades else pd.DataFrame()

    init_val   = float(initial_capital)
    final_val  = float(records_df["portfolio_value"].iloc[-1])
    total_ret  = (final_val / init_val - 1) * 100
    years      = (records_df.index[-1] - records_df.index[0]).days / 365.25
    cagr       = ((final_val / init_val) ** (1 / max(years, 0.01)) - 1) * 100

    rolling_max = records_df["portfolio_value"].cummax()
    drawdown    = (records_df["portfolio_value"] - rolling_max) / rolling_max
    mdd         = float(drawdown.min() * 100)

    # 연 변동성 / 샤프 지수
    daily_ret   = records_df["portfolio_value"].pct_change().dropna()
    vol_annual  = float(daily_ret.std() * np.sqrt(252) * 100)
    sharpe      = (cagr - 2.0) / vol_annual if vol_annual > 0 else 0.0  # 무위험 2% 가정

    return {
        "records":        records_df,
        "trades":         trades_df,
        "current_target": current_target,
        "metrics": {
            "initial_capital":  init_val,
            "final_value":      final_val,
            "total_return":     total_ret,
            "cagr":             cagr,
            "mdd":              mdd,
            "volatility":       vol_annual,
            "sharpe":           sharpe,
            "years":            years,
            "num_trades":       len(trades_df),
        },
    }


# ── 현재 신호 (실시간) ────────────────────────────────────────────────────
def get_live_signal(bull_momentum_pct: float = 0.75, bull_safe_pct: float = 0.25) -> dict | None:
    """최신 LAA 신호 계산 (yfinance 기준)"""
    prices = get_laa_prices(3)
    if prices.empty:
        return None

    as_of = prices.index[-1]
    canary, momentum, target = compute_laa_signal(
        prices, as_of,
        bull_momentum_pct=bull_momentum_pct,
        bull_safe_pct=bull_safe_pct,
    )

    if target is None:
        return None

    return {
        "as_of":        as_of,
        "canary_bull":  canary,
        "momentum":     momentum,
        "target":       target,
        "prices":       prices.iloc[-1].to_dict(),
        "spy_200sma":   float(prices["SPY"].tail(200).mean()),
    }


# ── 리밸런싱 주문 계산 ────────────────────────────────────────────────────
def compute_rebalance_orders(
    target: dict,
    current_holdings: dict,   # {symbol: shares}
    current_prices:   dict,   # {symbol: price_usd}
    total_usd: float,
) -> list[dict]:
    """
    목표 비중 vs 현재 보유량 비교 → 매수/매도 주문 목록 반환.
    current_holdings 에 없는 자산은 0주로 간주.
    수량은 정수(주) 단위.
    """
    orders = []

    for symbol, weight in target.items():
        price   = current_prices.get(symbol, 0)
        if price <= 0:
            continue
        target_shares = int(total_usd * weight / price)
        cur_shares    = int(current_holdings.get(symbol, 0))
        diff          = target_shares - cur_shares

        if diff > 0:
            orders.append({"symbol": symbol, "side": "매수", "qty": diff, "price": price})
        elif diff < 0:
            orders.append({"symbol": symbol, "side": "매도", "qty": abs(diff), "price": price})

    return orders
