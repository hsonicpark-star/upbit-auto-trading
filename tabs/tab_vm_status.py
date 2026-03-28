"""
VM 현황 탭 – VM 로컬 파일 읽기 전용

VM에서 실행되는 Streamlit이므로 data/*.json 파일을 직접 읽습니다.
vm_trader.py가 4시간마다 cron으로 실행되어 파일을 업데이트합니다.
"""
import json
import os
import streamlit as st

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

SIGNAL_COLORS = {
    "BUY":   "🟢",
    "SELL":  "🔴",
    "HOLD":  "🟡",
    "ERROR": "⚠️",
}


def _load(filename: str):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.warning(f"{filename} 읽기 실패: {e}")
        return None


def render():
    st.header("🖥️ VM 현황 (실시간 연동)")
    st.caption("VM cron이 4시간마다 vm_trader.py를 실행하여 data/*.json을 업데이트합니다.")

    col_refresh, col_info = st.columns([1, 5])
    with col_refresh:
        if st.button("🔄 새로고침"):
            st.rerun()
    with col_info:
        st.info("4시간마다 VM cron이 자동 업데이트합니다.")

    st.divider()

    # ── 신호 상태 ──────────────────────────────────────────────────────────
    signal_data = _load("signal_state.json")
    st.subheader("📊 현재 전략 신호")
    if signal_data:
        sig   = signal_data.get("signal", "?")
        emoji = SIGNAL_COLORS.get(sig, "❓")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("신호",     f"{emoji} {sig}")
        c2.metric("현재가",   f"{signal_data.get('current_price', 0):,.0f} 원")
        c3.metric("SMA29",    f"{signal_data.get('sma', 0):,.0f} 원")
        c4.metric("업데이트", signal_data.get("updated_at", "-"))

        with st.expander("📐 지표 상세"):
            st.json({
                "Donchian 상단 (115, 4H)": signal_data.get("donchian_upper"),
                "Donchian 하단 (105, 4H)": signal_data.get("donchian_lower"),
                "SMA 29 (1D)":             signal_data.get("sma"),
                "판단 근거":               signal_data.get("reason"),
            })
    else:
        st.warning("신호 데이터 없음. vm_trader.py를 실행하면 생성됩니다.")

    st.divider()

    # ── 잔고 ───────────────────────────────────────────────────────────────
    balance_data = _load("balance_cache.json")
    st.subheader("💰 잔고 현황")
    if balance_data:
        dry = "🧪 (DRY RUN)" if balance_data.get("dry_run") else ""
        st.caption(f"업데이트: {balance_data.get('updated_at', '-')} {dry}")
        balances = balance_data.get("balances", [])
        if isinstance(balances, list):
            rows = []
            for b in balances:
                cur    = b.get("currency", "")
                bal    = float(b.get("balance", 0))
                locked = float(b.get("locked", 0))
                avg    = float(b.get("avg_buy_price", 0))
                if bal + locked > 0:
                    rows.append({
                        "통화":       cur,
                        "보유량":     f"{bal:.8f}".rstrip("0").rstrip("."),
                        "주문중":     f"{locked:.8f}".rstrip("0").rstrip(".") if locked else "-",
                        "평균 매수가": f"{avg:,.0f}" if avg else "-",
                    })
            if rows:
                st.table(rows)
            else:
                st.info("보유 자산 없음")
        else:
            st.json(balances)
    else:
        st.warning("잔고 데이터 없음.")

    st.divider()

    # ── 거래 로그 ──────────────────────────────────────────────────────────
    trade_log = _load("trade_log.json")
    st.subheader("📋 실행 로그 (최근 50건)")
    if trade_log and isinstance(trade_log, list):
        for entry in trade_log[:50]:
            t      = entry.get("ts", "")
            etype  = entry.get("type", "")
            signal = entry.get("signal", "")
            price  = entry.get("price")
            dry    = "🧪" if entry.get("order", {}).get("status") == "DRY_RUN" else ""

            if etype == "ORDER":
                order  = entry.get("order", {})
                status = order.get("status", "")
                color  = "🟢" if status == "OK" else ("🧪" if status == "DRY_RUN" else "🔴")
                side   = "매수" if signal == "BUY" else "매도"
                st.write(f"`{t}` {color} **{side} 주문** {dry} | 가격: {price:,.0f}원" if price else f"`{t}` {color} **{side} 주문** {dry}")
            elif etype == "MANUAL":
                side = "매수" if entry.get("side") == "buy" else "매도"
                st.write(f"`{t}` 🔧 **수동 {side}** | {entry.get('ticker','')} {dry}")
            elif etype == "ERROR":
                st.write(f"`{t}` ⚠️ **오류** | {entry.get('detail', '')}")
            elif etype == "RUN":
                sig_e = SIGNAL_COLORS.get(signal, "")
                p_str = f"{price:,.0f}원" if price else ""
                st.write(f"`{t}` ▶️ 실행 | 신호: {sig_e} {signal} | {p_str} {dry}")

        if len(trade_log) > 50:
            st.caption(f"총 {len(trade_log)}건 중 50건 표시")
    else:
        st.info("거래 로그 없음. vm_trader.py 실행 후 생성됩니다.")
