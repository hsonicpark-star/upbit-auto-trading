"""
Tab: Grid Trading Backtest (그리드 매매 백테스트)
- OHLCV 히스토리 데이터 기반 그리드 매매 시뮬레이션
- 결과 지표: 총 수익, 체결 횟수, 거래당 수익, 최대 낙폭(MDD)
- 차트: 캔들 + 그리드 레벨 + 매수/매도 마커
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import pyupbit


# ─── 수수료 ──────────────────────────────────────────────────────────────────
FEE_RATE = 0.0005   # 업비트 0.05% 단방향

# ─── 캔들 interval 매핑 ──────────────────────────────────────────────────────
INTERVAL_OPTIONS = {
    "1분봉": "minute1",
    "5분봉": "minute5",
    "15분봉": "minute15",
    "1시간봉": "minute60",
    "4시간봉": "minute240",
    "일봉": "day",
}

COUNT_MAP = {
    "1분봉":  1440 * 7,    # 7일
    "5분봉":  288 * 14,    # 14일
    "15분봉": 96 * 30,     # 30일
    "1시간봉": 24 * 60,    # 60일
    "4시간봉": 6 * 90,     # 90일
    "일봉":   365,
}


# ─── 그리드 백테스트 엔진 ─────────────────────────────────────────────────────

def _round_price(price: float) -> float:
    """업비트 원화 마켓 최소 호가 단위 반올림"""
    if price >= 2_000_000:    unit = 1000
    elif price >= 1_000_000:  unit = 500
    elif price >= 500_000:    unit = 100
    elif price >= 100_000:    unit = 50
    elif price >= 10_000:     unit = 10
    elif price >= 1_000:      unit = 1
    else:                      unit = 0.1
    return round(round(price / unit) * unit, 1)


def run_backtest(
    df: pd.DataFrame,
    base_price: float,
    grid_count: int,
    grid_gap_pct: float,       # 소수 (예: 0.01 = 1%)
    total_invest: float,
    upper_limit: float,
    lower_limit: float,
    auto_reset: bool = True,
) -> dict:
    """
    그리드 매매 백테스트 시뮬레이션.

    각 캔들의 저가(low) / 고가(high)를 이용하여 그리드 레벨 교차 시
    체결로 처리합니다.

    Returns: dict {
        trades     : list of trade dicts,
        equity     : list of float (자산 추이, KRW),
        total_profit, total_fee, net_profit, win_count, lose_count,
        mdd, reset_count,
    }
    """
    order_amount = total_invest / grid_count

    # ── 그리드 레벨 생성 ──────────────────────────────────────────────────
    def make_grids(bp):
        grids = []
        for i in range(1, grid_count + 1):
            bp_float = float(bp)
            buy_price  = _round_price(bp_float * (1 - grid_gap_pct * i))
            sell_price = _round_price(bp_float * (1 + grid_gap_pct * i))
            grids.append({"level": -i, "price": buy_price,  "side": "buy",  "active": True})
            grids.append({"level":  i, "price": sell_price, "side": "sell", "active": False})
        return sorted(grids, key=lambda x: x["price"])

    grids = make_grids(base_price)
    upper = upper_limit
    lower = lower_limit

    trades = []
    equity_curve = []
    cash = total_invest          # 미투자 현금 (매수 체결 시 차감)
    coin_value = 0.0             # 보유 코인의 평가금액 (근사치)
    total_fee = 0.0
    reset_count = 0
    reset_log = []               # {index, price, reason}

    for idx, row in df.iterrows():
        low  = row["low"]
        high = row["high"]

        # ── 자동 재설정 (가격 이탈) ──────────────────────────────────────
        if auto_reset and (high > upper or low < lower):
            mid = (low + high) / 2
            grids = make_grids(mid)
            upper = _round_price(mid * (1 + grid_gap_pct * (grid_count + 1)))
            lower = _round_price(mid * (1 - grid_gap_pct * (grid_count + 1)))
            reset_count += 1
            reset_log.append({"ts": idx, "price": mid})
            cash = total_invest   # (단순화: 재설정 시 미투자 현금 리셋)

        # ── 각 그리드 레벨과 캔들 교차 확인 ─────────────────────────────
        for g in grids:
            price = g["price"]

            if g["side"] == "buy" and g["active"] and low <= price <= high:
                # 매수 체결
                vol  = order_amount / price
                fee  = order_amount * FEE_RATE
                g["active"] = False           # 이 레벨 매수 비활성화
                cash -= (order_amount + fee)
                total_fee += fee
                # 대응 매도 슬롯 활성화
                sell_target = _round_price(price * (1 + grid_gap_pct))
                for sg in grids:
                    if sg["side"] == "sell" and abs(sg["price"] - sell_target) / sell_target < 0.002:
                        sg["active"] = True
                        sg["buy_price"] = price
                        sg["volume"]    = vol
                        break
                trades.append({
                    "ts": idx, "side": "buy", "price": price,
                    "amount": order_amount, "fee": fee, "profit": None,
                })

            elif g["side"] == "sell" and g.get("active") and low <= price <= high:
                # 매도 체결 → 수익 실현
                vol       = g.get("volume", order_amount / g.get("buy_price", price))
                proceeds  = vol * price
                fee       = proceeds * FEE_RATE
                buy_cost  = vol * g.get("buy_price", price) * (1 + FEE_RATE)
                profit    = proceeds * (1 - FEE_RATE) - buy_cost
                g["active"] = False
                # 대응 매수 슬롯 재활성화
                buy_target = _round_price(price * (1 - grid_gap_pct))
                for bg in grids:
                    if bg["side"] == "buy" and abs(bg["price"] - buy_target) / buy_target < 0.002:
                        bg["active"] = True
                        break
                cash      += proceeds * (1 - FEE_RATE)
                total_fee += fee
                trades.append({
                    "ts": idx, "side": "sell", "price": price,
                    "amount": proceeds, "fee": fee, "profit": profit,
                })

        # 자산 추이 (현금 + 보유 코인 평가액 근사)
        equity_curve.append(cash)

    # ── 결과 집계 ─────────────────────────────────────────────────────────
    sell_trades   = [t for t in trades if t["side"] == "sell"]
    profits       = [t["profit"] for t in sell_trades if t["profit"] is not None]
    total_profit  = sum(profits)
    net_profit    = total_profit   # 수수료는 이미 profit에 반영됨
    win_count     = sum(1 for p in profits if p > 0)
    lose_count    = sum(1 for p in profits if p <= 0)

    # MDD (최대 낙폭) 계산
    eq = np.array(equity_curve, dtype=float)
    roll_max = np.maximum.accumulate(eq)
    drawdown = (eq - roll_max) / np.where(roll_max > 0, roll_max, 1)
    mdd = float(drawdown.min()) * 100   # %

    return {
        "trades":       trades,
        "equity":       equity_curve,
        "timestamps":   list(df.index),
        "total_profit": total_profit,
        "total_fee":    total_fee,
        "net_profit":   net_profit,
        "win_count":    win_count,
        "lose_count":   lose_count,
        "trade_count":  len(sell_trades),
        "mdd":          mdd,
        "reset_count":  reset_count,
        "reset_log":    reset_log,
        "avg_profit":   (total_profit / max(len(profits), 1)),
    }


# ─── 차트 생성 ───────────────────────────────────────────────────────────────

def _build_backtest_chart(df: pd.DataFrame, result: dict, grid_levels: list) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],
        subplot_titles=["가격 차트 + 그리드 매매", "누적 수익 (KRW)"],
        vertical_spacing=0.07,
    )

    # 캔들 차트
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"], high=df["high"],
        low=df["low"],   close=df["close"],
        name="캔들",
        increasing_line_color="#ef4444",
        decreasing_line_color="#3b82f6",
        increasing_fillcolor="#ef4444",
        decreasing_fillcolor="#3b82f6",
    ), row=1, col=1)

    # 그리드 레벨 수평선
    x_start = df.index[0]
    x_end   = df.index[-1]
    for lv in grid_levels:
        fig.add_shape(
            type="line", xref="x", yref="y",
            x0=x_start, x1=x_end, y0=lv, y1=lv,
            line=dict(color="rgba(255,200,0,0.25)", width=1, dash="dot"),
            row=1, col=1,
        )

    # 매수 / 매도 마커
    buy_trades  = [t for t in result["trades"] if t["side"] == "buy"]
    sell_trades = [t for t in result["trades"] if t["side"] == "sell"]

    if buy_trades:
        fig.add_trace(go.Scatter(
            x=[t["ts"] for t in buy_trades],
            y=[t["price"] for t in buy_trades],
            mode="markers",
            name="매수체결",
            marker=dict(symbol="triangle-up", size=9, color="#22c55e"),
        ), row=1, col=1)

    if sell_trades:
        fig.add_trace(go.Scatter(
            x=[t["ts"] for t in sell_trades],
            y=[t["price"] for t in sell_trades],
            mode="markers",
            name="매도체결",
            marker=dict(symbol="triangle-down", size=9, color="#f97316"),
        ), row=1, col=1)

    # 자동 재설정 수직선
    for r in result.get("reset_log", []):
        fig.add_vline(
            x=r["ts"], line_color="rgba(168,85,247,0.5)",
            line_dash="dash", line_width=1,
            annotation_text="↺재설정", annotation_font_size=9,
            row=1, col=1,
        )

    # 누적 수익 곡선
    ts   = result["timestamps"]
    sell_cumsum = []
    running = 0.0
    sell_idx = 0
    sell_times = {t["ts"]: t.get("profit", 0) or 0 for t in sell_trades}
    for t in ts:
        running += sell_times.get(t, 0.0)
        sell_cumsum.append(running)

    line_color = "#22c55e" if (sell_cumsum[-1] if sell_cumsum else 0) >= 0 else "#ef4444"
    fig.add_trace(go.Scatter(
        x=ts, y=sell_cumsum,
        fill="tozeroy",
        fillcolor="rgba(34,197,94,0.1)",
        line=dict(color=line_color, width=1.5),
        name="누적수익",
    ), row=2, col=1)

    fig.update_layout(
        height=600,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        margin=dict(l=0, r=0, t=50, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        font=dict(size=11),
    )
    return fig


# ─── 메인 render ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def _fetch_ohlcv(ticker: str, interval: str, count: int):
    """pyupbit 공개 API로 OHLCV 데이터 조회 (인증 불필요)"""
    return pyupbit.get_ohlcv(ticker, interval=interval, count=count)


def render(broker, ticker: str):
    st.subheader("📈 그리드 매매 백테스트")

    # 업비트 전용 기능 안내
    if not hasattr(broker, 'upbit'):
        st.warning(
            "⚠️ **그리드 백테스트는 업비트(Upbit) 전용 기능입니다.**\n\n"
            "사이드바에서 **업비트 (Upbit)** 를 선택한 후 사용해주세요."
        )
        return

    # ─── 설정 패널 ────────────────────────────────────────────────────────
    with st.expander("⚙️ 백테스트 설정", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            total_invest = st.number_input(
                "총 투자금액 (KRW)", min_value=10_000,
                value=st.session_state.get("bt_total_invest", 1_000_000),
                step=100_000, key="bt_total_invest",
            )
            grid_count = st.number_input(
                "그리드 개수 (상/하단 각각)", min_value=1, max_value=20,
                value=st.session_state.get("bt_grid_count", 5),
                step=1, key="bt_grid_count",
            )
        with col2:
            grid_gap_pct = st.number_input(
                "그리드 간격 (%)", min_value=0.1, max_value=50.0,
                value=st.session_state.get("bt_gap_pct", 1.0),
                step=0.1, format="%.2f", key="bt_gap_pct",
            )
            interval_label = st.selectbox(
                "캔들 단위", list(INTERVAL_OPTIONS.keys()),
                index=3,   # 기본: 1시간봉
                key="bt_interval",
            )
        with col3:
            upper_input = st.number_input(
                "상단 한계가 (0=자동)", min_value=0, value=0,
                step=1000, key="bt_upper",
                help="0이면 기준가 × (1 + 간격 × (그리드수+1)) 자동 계산"
            )
            lower_input = st.number_input(
                "하단 한계가 (0=자동)", min_value=0, value=0,
                step=1000, key="bt_lower",
                help="0이면 기준가 × (1 - 간격 × (그리드수+1)) 자동 계산"
            )
            auto_reset = st.toggle("가격 이탈 시 자동 재설정", value=True, key="bt_auto_reset")

    st.divider()

    run_btn = st.button("▶ 백테스트 실행", type="primary", use_container_width=False)
    if not run_btn:
        st.info("설정을 입력하고 **▶ 백테스트 실행** 버튼을 누르세요.")
        return

    # ─── 데이터 로드 ──────────────────────────────────────────────────────
    interval = INTERVAL_OPTIONS[interval_label]
    count    = COUNT_MAP[interval_label]

    with st.spinner(f"📡 {ticker} OHLCV {count}개 캔들 데이터 로딩 중..."):
        try:
            df = _fetch_ohlcv(ticker, interval, count)
        except Exception as e:
            st.error(f"데이터 조회 실패: {e}")
            return

    if df is None or df.empty:
        st.error("OHLCV 데이터를 불러오지 못했습니다.")
        return

    # ─── 백테스트 파라미터 계산 ───────────────────────────────────────────
    base_price  = float(df["close"].iloc[0])
    gap_decimal = grid_gap_pct / 100.0
    upper_limit = float(upper_input) if upper_input > 0 else _round_price(
        base_price * (1 + gap_decimal * (grid_count + 1))
    )
    lower_limit = float(lower_input) if lower_input > 0 else _round_price(
        base_price * (1 - gap_decimal * (grid_count + 1))
    )

    # 그리드 레벨 목록 (차트용)
    grid_levels = [
        _round_price(base_price * (1 + gap_decimal * i))
        for i in range(-grid_count, grid_count + 1)
    ]

    # ─── 백테스트 실행 ────────────────────────────────────────────────────
    with st.spinner("⚙️ 시뮬레이션 계산 중..."):
        result = run_backtest(
            df=df,
            base_price=base_price,
            grid_count=grid_count,
            grid_gap_pct=gap_decimal,
            total_invest=float(total_invest),
            upper_limit=upper_limit,
            lower_limit=lower_limit,
            auto_reset=auto_reset,
        )

    # ─── 결과 지표 ────────────────────────────────────────────────────────
    st.markdown("### 📊 백테스트 결과")
    net = result["net_profit"]
    ret_pct = net / total_invest * 100 if total_invest > 0 else 0

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("순 수익",       f"{net:+,.0f}원",
              delta=f"{ret_pct:+.2f}%",
              delta_color="normal")
    m2.metric("총 체결 횟수",  f"{result['trade_count']}회",
              f"승:{result['win_count']} / 패:{result['lose_count']}")
    m3.metric("거래당 평균수익", f"{result['avg_profit']:+,.0f}원")
    m4.metric("최대낙폭(MDD)", f"{result['mdd']:.2f}%")
    m5.metric("자동 재설정",   f"{result['reset_count']}회")

    st.divider()

    # ─── 차트 ─────────────────────────────────────────────────────────────
    fig = _build_backtest_chart(df, result, grid_levels)
    st.plotly_chart(fig, use_container_width=True)

    # ─── 거래 로그 테이블 ─────────────────────────────────────────────────
    with st.expander(f"📋 거래 내역 (총 {len(result['trades'])}건)", expanded=False):
        trade_rows = []
        for t in result["trades"]:
            trade_rows.append({
                "시각":       t["ts"].strftime("%Y-%m-%d %H:%M") if hasattr(t["ts"], "strftime") else str(t["ts"]),
                "구분":       "🔵 매수" if t["side"] == "buy" else "🔴 매도",
                "체결가(KRW)": f"{t['price']:,.0f}",
                "금액(KRW)":  f"{t['amount']:,.0f}",
                "수수료(KRW)": f"{t['fee']:,.1f}",
                "수익(KRW)":  f"{t['profit']:+,.0f}" if t.get("profit") is not None else "—",
            })
        if trade_rows:
            st.dataframe(pd.DataFrame(trade_rows), use_container_width=True, hide_index=True)
        else:
            st.info("체결된 거래가 없습니다. 그리드 간격 또는 기간을 조정해보세요.")

    # ─── 파라미터 요약 ────────────────────────────────────────────────────
    st.caption(
        f"📌 시뮬레이션 기간: {df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')} "
        f"({len(df)}캔들 · {interval_label}) | "
        f"기준가: {base_price:,.0f}원 | "
        f"범위: {lower_limit:,.0f}~{upper_limit:,.0f}원 | "
        f"그리드 {grid_count}개 × {grid_gap_pct:.2f}% | "
        f"그리드당 {total_invest/grid_count:,.0f}원"
    )
