"""
Tab: Grid Trading (그리드 매매)
- 설정 패널: 투자금, 그리드 수, 간격%, 상/하단 가격 한계
- 시작/정지 버튼
- 그리드 현황 테이블 + 누적 수익
- 실시간 자동 새로고침 (3초)
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
from strategy_grid import GridStrategy
from tabs.tab_log import add_log


# ─── 세션 상태 키 ──────────────────────────────────────────────────────────
_KEY_STRATEGY = "grid_strategy"
_KEY_RUNNING  = "grid_running"
_KEY_TICKER   = "grid_ticker"


def _get_strategy() -> GridStrategy | None:
    return st.session_state.get(_KEY_STRATEGY)


def _status_badge(status: str) -> str:
    return {
        "wait":      "🟡 대기",
        "done":      "✅ 체결",
        "empty":     "⬜ 빈슬롯",
        "error":     "❌ 오류",
        "cancelled": "🚫 취소",
    }.get(status, status)


def _side_badge(side: str) -> str:
    return "🔵 매수" if side == "buy" else "🔴 매도"


def _build_grid_df(grids: list, base_price: float, current_price: float) -> pd.DataFrame:
    rows = []
    for g in grids:
        price = g["price"]
        diff_pct = ((price - base_price) / base_price * 100) if base_price > 0 else 0.0
        is_current = abs(price - current_price) / current_price < 0.005 if current_price > 0 else False
        rows.append({
            "레벨":       f"{'▶' if is_current else '  '} {g['level']:+d}",
            "가격(KRW)":  f"{price:,}",
            "등락":       f"{diff_pct:+.2f}%",
            "구분":       _side_badge(g["side"]),
            "상태":       _status_badge(g["status"]),
            "체결횟수":   g["filled_count"],
            "수익(KRW)":  f"{g['profit']:+,.0f}" if g["profit"] != 0 else "—",
        })
    return pd.DataFrame(rows)


def render(broker, ticker: str):
    st.subheader("🔲 실시간 그리드 매매")

    strategy: GridStrategy | None = _get_strategy()
    is_running = st.session_state.get(_KEY_RUNNING, False)

    # ─── 현황 지표 (실행 중일 때) ─────────────────────────────────────────
    if is_running and strategy:
        # 자동 재설정 + 체결 감지 실행
        try:
            current_price = broker.get_current_price(ticker)
            reset_triggered = strategy.auto_reset_if_out_of_range(current_price)
            if not reset_triggered:
                strategy.check_and_reorder()
        except Exception as e:
            add_log(f"[그리드] 루프 오류: {e}", "ERROR")

        status = strategy.get_status()
        current_price = status["current_price"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("현재가", f"{current_price:,.0f}원",
                  f"기준가 {status['base_price']:,.0f}원 대비")
        c2.metric("누적 수익", f"{status['total_profit']:+,.0f}원")
        c3.metric("자동 재설정", f"{status['reset_count']}회")
        c4.metric(
            "그리드 범위",
            f"{status['lower_limit']:,.0f}~{status['upper_limit']:,.0f}",
            f"간격 {status['grid_gap_pct']:.2f}%"
        )
        st.divider()

    # ─── 설정 패널 ────────────────────────────────────────────────────────
    with st.expander("⚙️ 그리드 설정", expanded=not is_running):
        col1, col2 = st.columns(2)
        with col1:
            total_invest = st.number_input(
                "총 투자금액 (KRW)", min_value=10_000,
                value=st.session_state.get("grid_total_invest", 100_000),
                step=10_000, key="grid_total_invest",
                help="그리드 레벨당 투자금 = 총 투자금 / 그리드 개수"
            )
            grid_count = st.number_input(
                "그리드 개수 (상/하단 각각)", min_value=1, max_value=20,
                value=st.session_state.get("grid_count", 5),
                step=1, key="grid_count",
                help="현재가 위아래로 각각 N개의 레벨을 생성합니다"
            )
        with col2:
            grid_gap_pct = st.number_input(
                "그리드 간격 (%)", min_value=0.1, max_value=50.0,
                value=st.session_state.get("grid_gap_pct", 1.0),
                step=0.1, format="%.2f", key="grid_gap_pct",
                help="인접한 그리드 레벨 간의 가격 간격 비율. 수수료(왕복 0.1%) 이상 설정 권장 → 최소 0.2%"
            )
            order_amount_display = total_invest / max(grid_count, 1)
            st.info(f"**그리드당 주문금액**: {order_amount_display:,.0f}원\n\n"
                    f"(최소 주문금액 5,000원 이상이어야 합니다)")

        st.markdown("**가격 한계 설정 (선택사항 — 비워두면 자동 계산)**")
        col3, col4 = st.columns(2)
        with col3:
            upper_input = st.number_input(
                "상단 한계가 (KRW, 0=자동)", min_value=0,
                value=st.session_state.get("grid_upper", 0),
                step=1000, key="grid_upper",
                help=f"0 입력 시: 기준가 × (1 + 간격% × (그리드수+1)) 으로 자동 계산"
            )
        with col4:
            lower_input = st.number_input(
                "하단 한계가 (KRW, 0=자동)", min_value=0,
                value=st.session_state.get("grid_lower", 0),
                step=1000, key="grid_lower",
                help="0 입력 시: 기준가 × (1 - 간격% × (그리드수+1)) 으로 자동 계산"
            )

        upper_limit = float(upper_input) if upper_input > 0 else None
        lower_limit = float(lower_input) if lower_input > 0 else None

        # 유효성 검토
        per_order = total_invest / max(grid_count, 1)
        warnings = []
        if per_order < 5000:
            warnings.append(f"⚠️ 그리드당 주문금액({per_order:,.0f}원)이 업비트 최소 주문금액(5,000원) 미만입니다.")
        if grid_gap_pct < 0.2:
            warnings.append("⚠️ 그리드 간격이 수수료(왕복 약 0.1%)보다 작아 수익이 마이너스가 될 수 있습니다.")
        for w in warnings:
            st.warning(w)

    # ─── 시작 / 정지 버튼 ────────────────────────────────────────────────
    st.divider()
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 4])

    with btn_col1:
        start_clicked = st.button(
            "▶ 시작", type="primary",
            disabled=is_running or bool(warnings),
            use_container_width=True,
        )
    with btn_col2:
        stop_clicked = st.button(
            "⏹ 정지", type="secondary",
            disabled=not is_running,
            use_container_width=True,
        )

    if start_clicked:
        new_strategy = GridStrategy(
            broker=broker,
            ticker=ticker,
            total_invest=float(total_invest),
            grid_count=int(grid_count),
            grid_gap_pct=float(grid_gap_pct),
            upper_limit=upper_limit,
            lower_limit=lower_limit,
        )
        new_strategy.initialize_grids()
        st.session_state[_KEY_STRATEGY] = new_strategy
        st.session_state[_KEY_RUNNING]  = True
        st.session_state[_KEY_TICKER]   = ticker
        add_log(f"[그리드] 봇 시작 — {ticker} / 투자금 {total_invest:,}원 / {grid_count}개 / {grid_gap_pct}%", "INFO")
        st.rerun()

    if stop_clicked and strategy:
        strategy.stop()
        st.session_state[_KEY_RUNNING] = False
        add_log(f"[그리드] 봇 정지 — 미체결 주문 취소 완료", "INFO")
        st.rerun()

    # ─── 그리드 현황 테이블 ───────────────────────────────────────────────
    if strategy:
        status = strategy.get_status()
        st.markdown("### 📊 그리드 레벨 현황")

        grid_df = _build_grid_df(
            status["grids"],
            status["base_price"],
            status["current_price"],
        )
        if not grid_df.empty:
            st.dataframe(grid_df, use_container_width=True, hide_index=True)

            # 요약 지표
            total_filled = sum(g["filled_count"] for g in status["grids"])
            wait_count   = sum(1 for g in status["grids"] if g["status"] == "wait")
            st.caption(
                f"💼 총 체결: {total_filled}회 | 대기 주문: {wait_count}건 | "
                f"기준가: {status['base_price']:,.0f}원 | "
                f"마지막 업데이트: {datetime.now().strftime('%H:%M:%S')}"
            )
        else:
            st.info("그리드가 아직 초기화되지 않았습니다.")

        # ─── 내부 로그 ────────────────────────────────────────────────────
        with st.expander("🗒️ 그리드 봇 내부 로그", expanded=False):
            for entry in status["logs"]:
                level = entry.get("level", "INFO")
                color = {"ERROR": "red", "WARNING": "orange"}.get(level, "gray")
                st.markdown(
                    f"<span style='color:{color};font-size:0.82em'>"
                    f"[{entry['time']}] [{level}] {entry['msg']}</span>",
                    unsafe_allow_html=True,
                )

    else:
        st.info("▶ 시작 버튼을 눌러 그리드 매매를 시작하세요.")

    # ─── 자동 새로고침 (실행 중일 때만) ───────────────────────────────────
    if is_running:
        st_autorefresh(interval=3_000, key="grid_refresh")
