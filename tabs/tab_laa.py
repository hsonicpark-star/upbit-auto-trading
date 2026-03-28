"""
Tab: LAA Strategy (LAA 전략 - 한국투자증권 해외주식)
-------------------------------------------------------
LAA (Lethargic Asset Allocation)
- Universe : SPY, IWM, GLD, BIL
- Canary   : SPY > 200일 SMA
- 강세장   : 모멘텀 1위 자산 75% + BIL 25%
- 약세장   : BIL 100%
- 리밸런싱 : 월 / 분기 / 반기 / 년 선택
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

from strategy_laa import (
    LAA_ASSETS, REBALANCE_PERIODS, MOMENTUM_ASSETS, SAFE_ASSET,
    get_laa_prices, compute_laa_signal, backtest_laa,
    get_live_signal, compute_rebalance_orders,
)


# ── 공통 포맷 헬퍼 ──────────────────────────────────────────────────────────
def _pct(v): return f"{v:+.2f}%"
def _usd(v): return f"${v:,.2f}"
def _fmt_krw(v): return f"₩{v:,.0f}"


def render(broker):
    st.subheader("📊 LAA 전략 (한국투자증권 해외 ETF)")
    st.caption("Lethargic Asset Allocation | SPY · IWM · GLD · BIL | 한국투자증권 실전계좌")

    tab_bt, tab_live = st.tabs(["📈 백테스트", "🚀 LIVE 트레이딩"])

    # ════════════════════════════════════════════════════════════════════════
    # 백테스트 탭
    # ════════════════════════════════════════════════════════════════════════
    with tab_bt:
        _render_backtest()

    # ════════════════════════════════════════════════════════════════════════
    # LIVE 트레이딩 탭
    # ════════════════════════════════════════════════════════════════════════
    with tab_live:
        _render_live(broker)


# ── 백테스트 ──────────────────────────────────────────────────────────────
def _render_backtest():
    st.markdown("#### ⚙️ 백테스트 설정")

    col1, col2, col3 = st.columns(3)
    with col1:
        period_years = st.selectbox("백테스트 기간", [3, 5, 7, 10, 15, 20], index=1)
    with col2:
        rebal_label = st.selectbox("리밸런싱 주기", list(REBALANCE_PERIODS.keys()), index=0)
    with col3:
        initial_usd = st.number_input("초기 자본 (USD)", value=10_000, step=1_000, min_value=1_000)

    period_months = REBALANCE_PERIODS[rebal_label]

    if st.button("▶ 백테스트 실행", type="primary", key="laa_backtest_run"):
        with st.spinner("데이터 수집 및 시뮬레이션 중..."):
            result = backtest_laa(
                period_years=period_years,
                initial_capital=float(initial_usd),
                period_months=period_months,
            )

        if result is None:
            st.error("데이터 수집 실패. 인터넷 연결을 확인하세요.")
            return

        st.session_state["laa_bt_result"] = result

    # 결과 표시
    if "laa_bt_result" not in st.session_state:
        st.info("백테스트 실행 버튼을 눌러주세요.")
        return

    result = st.session_state["laa_bt_result"]
    m      = result["metrics"]
    recs   = result["records"]
    trades = result["trades"]

    # ── 성과 지표 ──
    st.divider()
    st.markdown("#### 📋 성과 지표")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("최종 자산", _usd(m["final_value"]),   _pct(m["total_return"]))
    c2.metric("CAGR (연복리)",  _pct(m["cagr"]))
    c3.metric("MDD",            _pct(m["mdd"]))
    c4.metric("연 변동성",      _pct(m["volatility"]))
    c5.metric("샤프 지수",      f"{m['sharpe']:.2f}")

    col_a, col_b = st.columns(2)
    col_a.metric("초기 자본",   _usd(m["initial_capital"]))
    col_b.metric("총 거래 횟수", f"{m['num_trades']}건")

    # ── 자산 가치 차트 ──
    st.divider()
    st.markdown("#### 📉 포트폴리오 가치 추이")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=recs.index, y=recs["portfolio_value"],
        mode="lines", name="LAA 포트폴리오",
        line=dict(color="#00c4ff", width=2),
        fill="tozeroy", fillcolor="rgba(0,196,255,0.08)"
    ))

    # 리밸런싱 시점 마커
    rebal_rows = recs[recs["is_rebal"]]
    fig.add_trace(go.Scatter(
        x=rebal_rows.index, y=rebal_rows["portfolio_value"],
        mode="markers", name="리밸런싱",
        marker=dict(symbol="triangle-up", size=8, color="orange"),
    ))

    fig.update_layout(
        height=400, hovermode="x unified",
        xaxis_title="날짜", yaxis_title="자산 (USD)",
        legend=dict(orientation="h", y=1.05),
        margin=dict(l=0, r=0, t=30, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── 거래 내역 ──
    if not trades.empty:
        st.divider()
        st.markdown("#### 🗒️ 리밸런싱 거래 내역")
        st.dataframe(
            trades.style.map(
                lambda v: "color:#ff4b4b" if v == "매도" else ("color:#00c4ff" if v == "매수" else ""),
                subset=["구분"]
            ),
            use_container_width=True, height=300
        )


# ── LIVE 트레이딩 ─────────────────────────────────────────────────────────
def _render_live(broker):
    st.markdown("#### 🔴 실시간 LAA 신호")

    # 브로커 체크
    broker_key = st.session_state.get("broker_key", "")
    if "kis" not in broker_key:
        st.warning("⚠️ LAA LIVE 트레이딩은 한국투자증권 계좌를 선택해야 합니다.")
        return

    # ── 리밸런싱 주기 설정
    st.markdown("#### ⚙️ LIVE 설정")
    col1, col2 = st.columns(2)
    with col1:
        rebal_label = st.selectbox("리밸런싱 주기 ", list(REBALANCE_PERIODS.keys()), index=0, key="live_rebal")
    with col2:
        usd_krw = st.number_input("USD/KRW 환율", value=1380, step=10, min_value=1000)

    # ── 현재 신호 조회
    if st.button("🔄 신호 새로고침", key="laa_refresh"):
        with st.spinner("LAA 신호 계산 중..."):
            signal = get_live_signal()
        st.session_state["laa_signal"] = signal

    signal = st.session_state.get("laa_signal")

    if signal is None:
        st.info("'신호 새로고침' 버튼을 눌러 현재 신호를 확인하세요.")
        if st.button("지금 확인", key="laa_first_check"):
            with st.spinner("LAA 신호 계산 중..."):
                signal = get_live_signal()
            st.session_state["laa_signal"] = signal
            st.rerun()
        return

    # ── 신호 표시
    st.divider()
    canary   = signal["canary_bull"]
    momentum = signal.get("momentum", {})
    target   = signal.get("target", {})
    prices   = signal.get("prices", {})
    spy_sma  = signal.get("spy_200sma", 0)
    as_of    = signal["as_of"]

    col_s, col_m = st.columns([1, 2])

    with col_s:
        st.markdown("**📡 캐너리 신호 (SPY > 200일 SMA)**")
        if canary:
            st.success(f"🟢 강세장\nSPY: ${prices.get('SPY', 0):.2f} > SMA: ${spy_sma:.2f}")
        else:
            st.error(f"🔴 약세장\nSPY: ${prices.get('SPY', 0):.2f} < SMA: ${spy_sma:.2f}")
        st.caption(f"기준일: {as_of.strftime('%Y-%m-%d')}")

    with col_m:
        st.markdown("**📊 12개월 모멘텀**")
        for asset in MOMENTUM_ASSETS:
            mom = momentum.get(asset, 0)
            bar = "🟢" if mom > 0 else "🔴"
            st.write(f"{bar} **{asset}** ({LAA_ASSETS[asset]['name']}): {_pct(mom)}")
        st.write(f"⚪ **BIL** ({LAA_ASSETS['BIL']['name']}): 방어 자산 (모멘텀 미비교)")

    # ── 목표 비중
    st.divider()
    st.markdown("**🎯 목표 포트폴리오 배분**")
    cols = st.columns(len(target))
    for i, (sym, w) in enumerate(target.items()):
        with cols[i]:
            st.metric(sym, f"{w*100:.0f}%", LAA_ASSETS[sym]["name"])

    # ── 현재 보유 / 주문 계산
    st.divider()
    st.markdown("#### 💼 현재 보유 현황 & 리밸런싱 주문")

    if st.button("📥 KIS 잔고 조회 및 주문 계산", key="laa_calc_orders"):
        with st.spinner("잔고 조회 중..."):
            try:
                overseas = broker.get_overseas_balances()
                st.session_state["laa_overseas"] = overseas
            except Exception as e:
                st.error(f"잔고 조회 실패: {e}")
                st.session_state["laa_overseas"] = None

    overseas = st.session_state.get("laa_overseas")

    if overseas is None:
        st.info("'KIS 잔고 조회 및 주문 계산' 버튼을 눌러주세요.")
        return

    usd_cash = overseas.get("usd_balance", 0)
    holdings_list = overseas.get("holdings", [])

    # 현재 보유 테이블
    holdings_df = pd.DataFrame(holdings_list) if holdings_list else pd.DataFrame(
        columns=["symbol", "quantity", "avg_price", "current_price", "eval_amount"]
    )
    st.markdown(f"**달러 예수금:** {_usd(usd_cash)}")
    if not holdings_df.empty:
        st.dataframe(holdings_df, use_container_width=True)
    else:
        st.info("보유 해외 주식 없음")

    # 총 자산 (USD)
    holdings_dict = {row["symbol"]: row["quantity"] for _, row in holdings_df.iterrows()} if not holdings_df.empty else {}
    eval_sum      = sum(r["eval_amount"] for r in holdings_list)
    total_usd     = usd_cash + eval_sum

    st.metric("총 해외 자산 (USD)", _usd(total_usd), f"≈ {_fmt_krw(total_usd * usd_krw)}")

    # 주문 계산
    orders = compute_rebalance_orders(target, holdings_dict, prices, total_usd)

    st.divider()
    st.markdown("**📋 리밸런싱 필요 주문**")

    if not orders:
        st.success("✅ 현재 포트폴리오가 목표 비중과 일치합니다. 리밸런싱 불필요.")
        return

    for order in orders:
        color = "🟢" if order["side"] == "매수" else "🔴"
        est   = order["qty"] * order["price"]
        st.write(f"{color} **{order['symbol']}** {order['side']} {order['qty']}주 "
                 f"@ ${order['price']:.2f} ≈ {_usd(est)}")

    st.divider()

    # ── 실제 주문 실행
    st.markdown("#### ⚠️ 리밸런싱 실행")
    st.warning("아래 버튼을 누르면 KIS 실전 계좌에 실제 주문이 발생합니다.")

    confirm = st.checkbox("위 주문 내역을 확인했으며 실행에 동의합니다.", key="laa_confirm")

    if confirm and st.button("🚀 리밸런싱 실행", type="primary", key="laa_execute"):
        results = []
        for order in orders:
            symbol   = order["symbol"]
            qty      = order["qty"]
            price    = order["price"]
            exchange = LAA_ASSETS[symbol]["exchange_order"]

            try:
                if order["side"] == "매수":
                    res = broker.buy_overseas(symbol, price, qty, exchange)
                else:
                    res = broker.sell_overseas(symbol, price, qty, exchange)

                if res:
                    results.append(f"✅ {symbol} {order['side']} {qty}주 → 주문번호: {res.get('uuid')}")
                else:
                    results.append(f"❌ {symbol} {order['side']} 실패")
            except Exception as e:
                results.append(f"❌ {symbol} 오류: {e}")

        for r in results:
            st.write(r)

        # 세션 초기화
        st.session_state.pop("laa_overseas", None)
        st.session_state.pop("laa_signal", None)
        st.success("리밸런싱 주문 완료! 잔고를 다시 조회해 확인하세요.")
