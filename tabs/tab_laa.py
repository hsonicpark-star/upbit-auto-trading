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
import plotly.graph_objects as go

from strategy_laa import (
    LAA_ASSETS, REBALANCE_PERIODS, MOMENTUM_ASSETS, SAFE_ASSET,
    backtest_laa, get_live_signal, compute_rebalance_orders,
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
def _allocation_settings(key_prefix: str):
    """강세장 자산 배분 슬라이더 (공통 UI). (모멘텀비중, 방어비중) 반환."""
    with st.expander("⚙️ 자산 배분 커스터마이징 (기본값: 강세장 75% / 방어 25%)", expanded=False):
        st.caption("강세장: 모멘텀 1위 ETF + BIL(방어) | 약세장: BIL 100% 자동 적용")
        col_a, col_b = st.columns(2)
        with col_a:
            momentum_pct = st.slider(
                "모멘텀 1위 자산 비중 (%)",
                min_value=10, max_value=100, value=75, step=5,
                key=f"{key_prefix}_momentum_pct",
            )
        with col_b:
            safe_pct = 100 - momentum_pct
            st.metric("방어 자산 (BIL) 비중", f"{safe_pct}%")

        # 예시 표시
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f"**SPY** 또는\n**IWM** 또는\n**GLD**\n\n→ {momentum_pct}%")
        c2.markdown(f"**BIL**\n(방어)\n\n→ {safe_pct}%")
        c3.markdown("**약세장시**\nBIL\n\n→ 100%")
        c4.markdown(f"*리밸런싱: {momentum_pct}+{safe_pct}=100%*")

    return momentum_pct / 100, safe_pct / 100


def _render_backtest_weights(key_prefix: str = "bt"):
    """백테스트용 종목별 비중 설정 (현재가 없이 비중만)"""
    st.markdown("**종목별 비중 설정 (합계 = 100%)**")
    cols = st.columns(len(LAA_ASSETS))
    weights = {}
    for i, asset in enumerate(LAA_ASSETS):
        with cols[i]:
            is_safe = (asset == SAFE_ASSET)
            label = f"{'🛡 ' if is_safe else ''}{asset}"
            w = st.number_input(
                label, value=25, min_value=0, max_value=100, step=5,
                key=f"{key_prefix}_w_{asset}",
            )
            st.caption(LAA_ASSETS[asset]["name"])
            weights[asset] = w
    total_w = sum(weights.values())
    if total_w != 100:
        st.warning(f"⚠️ 비중 합계: {total_w}% (100%가 되어야 합니다)")
    else:
        st.success(f"✅ 비중 합계: {total_w}%")
    return {a: w / 100 for a, w in weights.items() if w > 0}


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

    # ── 배분 모드 선택
    st.divider()
    mode = st.radio(
        "배분 모드",
        ["🎯 동적 LAA (캐너리 신호 + 모멘텀)", "📊 정적 배분 (비중 고정)"],
        horizontal=True, key="bt_mode",
    )

    static_weights = None
    bull_momentum_pct, bull_safe_pct = 0.75, 0.25

    if mode.startswith("📊"):
        static_weights = _render_backtest_weights("bt")
    else:
        bull_momentum_pct, bull_safe_pct = _allocation_settings("bt")

    if st.button("▶ 백테스트 실행", type="primary", key="laa_backtest_run"):
        with st.spinner("데이터 수집 및 시뮬레이션 중..."):
            result = backtest_laa(
                period_years=period_years,
                initial_capital=float(initial_usd),
                period_months=period_months,
                bull_momentum_pct=bull_momentum_pct,
                bull_safe_pct=bull_safe_pct,
                static_weights=static_weights,
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


# ── 자산 배분 계산기 테이블 ────────────────────────────────────────────────
def _render_allocation_table(prices: dict, key_prefix: str = "live"):
    """종목 / 비중(조절) / 현재가 / 목표금액 / 매수수량 / 실제투자액 테이블"""

    col_inv, col_hint = st.columns([1, 2])
    with col_inv:
        total_investment = st.number_input(
            "투자금 ($)", value=10_000, step=1_000, min_value=100,
            key=f"{key_prefix}_total_invest",
        )
    with col_hint:
        st.info("투자금을 입력하면 매수 수량이 자동 계산됩니다")

    # 헤더
    H = st.columns([2, 1.2, 1.8, 1.8, 1.8, 1.8])
    for col, label in zip(H, ["종목", "비중", "현재가", "목표금액", "매수 수량", "실제 투자액"]):
        col.markdown(f"**{label}**")
    st.divider()

    weights      = {}
    total_actual = 0.0
    total_shares = 0

    for asset in LAA_ASSETS:
        is_safe = (asset == SAFE_ASSET)
        C = st.columns([2, 1.2, 1.8, 1.8, 1.8, 1.8])

        with C[0]:
            badge = " &nbsp;<span style='background:#f0a500;color:#fff;padding:2px 6px;border-radius:4px;font-size:12px'>방어</span>" if is_safe else ""
            st.markdown(f"**{asset}**{badge}<br><small style='color:gray'>{LAA_ASSETS[asset]['name']}</small>",
                        unsafe_allow_html=True)

        with C[1]:
            w = st.number_input(
                "비중", value=25, min_value=0, max_value=100, step=5,
                key=f"{key_prefix}_w_{asset}", label_visibility="collapsed",
            )
            weights[asset] = w

        price      = prices.get(asset, 0)
        target_usd = total_investment * w / 100
        shares     = int(target_usd / price) if price > 0 else 0
        actual     = shares * price
        total_actual  += actual
        total_shares  += shares

        C[2].markdown(f"${price:,.2f}" if price else "-")
        C[3].markdown(f"${target_usd:,.0f}")
        C[4].markdown(f"**{shares}주**")
        C[5].markdown(f"${actual:,.2f}")

    st.divider()

    # 합계 행
    total_w = sum(weights.values())
    TC = st.columns([2, 1.2, 1.8, 1.8, 1.8, 1.8])
    TC[0].markdown("**합계**")
    TC[1].markdown(f"**{total_w}%**" + (" ⚠️" if total_w != 100 else "")  )
    TC[3].markdown(f"**${total_investment:,.0f}**")
    TC[4].markdown(f"**{total_shares}주**")
    TC[5].markdown(f"**${total_actual:,.2f}**")

    # 잔여 현금 행
    remaining = total_investment - total_actual
    RC = st.columns([2, 1.2, 1.8, 1.8, 1.8, 1.8])
    RC[0].markdown("<small>잔여 현금 (정수주 매수 후)</small>", unsafe_allow_html=True)
    RC[5].markdown(f"${remaining:,.2f}")

    if total_w != 100:
        st.warning(f"⚠️ 비중 합계: {total_w}% (100%가 되어야 합니다)")

    # 0~1 스케일로 변환
    target_weights = {a: w / 100 for a, w in weights.items() if w > 0}
    return target_weights, total_investment


# ── LIVE 트레이딩 ─────────────────────────────────────────────────────────
def _render_live(broker):
    st.markdown("#### 🔴 실시간 LAA 신호")

    # 브로커 체크
    broker_key = st.session_state.get("broker_key", "")
    if "kis" not in broker_key:
        st.warning("⚠️ LAA LIVE 트레이딩은 한국투자증권 계좌를 선택해야 합니다.")
        return

    # ── 기본 설정
    col1, col2 = st.columns(2)
    with col1:
        st.selectbox("리밸런싱 주기 ", list(REBALANCE_PERIODS.keys()), index=0, key="live_rebal")
    with col2:
        usd_krw = st.number_input("USD/KRW 환율", value=1380, step=10, min_value=1000)

    # ── 신호 새로고침 (현재가 포함)
    if st.button("🔄 신호 / 현재가 새로고침", key="laa_refresh"):
        with st.spinner("LAA 신호 계산 중..."):
            signal = get_live_signal()
        st.session_state["laa_signal"] = signal

    signal = st.session_state.get("laa_signal")

    if signal is None:
        st.info("'신호 / 현재가 새로고침' 버튼을 눌러 현재가를 가져오세요.")
        if st.button("지금 확인", key="laa_first_check"):
            with st.spinner("LAA 신호 계산 중..."):
                signal = get_live_signal()
            st.session_state["laa_signal"] = signal
            st.rerun()
        return

    prices  = signal.get("prices", {})
    canary  = signal["canary_bull"]
    momentum = signal.get("momentum", {})
    spy_sma  = signal.get("spy_200sma", 0)
    as_of    = signal["as_of"]

    # ── 캐너리 신호 & 모멘텀 (간략)
    col_s, col_m = st.columns([1, 2])
    with col_s:
        st.markdown("**📡 캐너리 신호**")
        if canary:
            st.success(f"🟢 강세장  \nSPY ${prices.get('SPY',0):.2f} > SMA ${spy_sma:.2f}")
        else:
            st.error(f"🔴 약세장  \nSPY ${prices.get('SPY',0):.2f} < SMA ${spy_sma:.2f}")
        st.caption(f"기준일: {as_of.strftime('%Y-%m-%d')}")
    with col_m:
        st.markdown("**📊 12개월 모멘텀**")
        for asset in MOMENTUM_ASSETS:
            mom = momentum.get(asset, 0)
            bar = "🟢" if mom > 0 else "🔴"
            st.write(f"{bar} **{asset}**: {_pct(mom)}")
        st.write("⚪ **BIL**: 방어 자산")

    # ── 자산 배분 계산기
    st.divider()
    st.markdown("#### 💼 자산 배분 계산기")
    target_weights, total_investment = _render_allocation_table(prices, key_prefix="live")

    # ── KIS 잔고 조회 & 리밸런싱
    st.divider()
    st.markdown("#### 📥 리밸런싱 주문")

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

    usd_cash      = overseas.get("usd_balance", 0)
    holdings_list = overseas.get("holdings", [])
    holdings_df   = pd.DataFrame(holdings_list) if holdings_list else pd.DataFrame(
        columns=["symbol", "quantity", "avg_price", "current_price", "eval_amount"]
    )

    st.markdown(f"**달러 예수금:** {_usd(usd_cash)}")
    if not holdings_df.empty:
        st.dataframe(holdings_df, use_container_width=True, hide_index=True)
    else:
        st.info("보유 해외 주식 없음")

    holdings_dict = {row["symbol"]: row["quantity"] for _, row in holdings_df.iterrows()} if not holdings_df.empty else {}
    eval_sum      = sum(r["eval_amount"] for r in holdings_list)
    total_usd     = usd_cash + eval_sum
    st.metric("총 해외 자산 (USD)", _usd(total_usd), f"≈ {_fmt_krw(total_usd * usd_krw)}")

    orders = compute_rebalance_orders(target_weights, holdings_dict, prices, total_usd)

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
                results.append(f"✅ {symbol} {order['side']} {qty}주" if res else f"❌ {symbol} {order['side']} 실패")
            except Exception as e:
                results.append(f"❌ {symbol} 오류: {e}")

        for r in results:
            st.write(r)

        st.session_state.pop("laa_overseas", None)
        st.session_state.pop("laa_signal", None)
        st.success("리밸런싱 주문 완료! 잔고를 다시 조회해 확인하세요.")
