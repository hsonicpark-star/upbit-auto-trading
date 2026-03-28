"""
VM 현황 탭 – 로컬 Streamlit (읽기 전용)

GitHub Raw URL에서 data/ JSON 파일을 읽어 표시합니다.
로컬 PC가 꺼져 있어도 VM이 계속 업데이트하며,
Streamlit은 GitHub에서 최신 JSON을 가져오기만 합니다.
"""
import json
import streamlit as st
import requests
from datetime import datetime

# GitHub Raw URL 기본 경로 (repo main 브랜치)
GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/"
    "hsonicpark-star/upbit-auto-trading/master/data"
)

URLS = {
    "balance":  f"{GITHUB_RAW_BASE}/balance_cache.json",
    "signal":   f"{GITHUB_RAW_BASE}/signal_state.json",
    "trade_log":f"{GITHUB_RAW_BASE}/trade_log.json",
}

SIGNAL_COLORS = {
    "BUY":   "🟢",
    "SELL":  "🔴",
    "HOLD":  "🟡",
    "ERROR": "⚠️",
}


def _fetch(url: str) -> dict | list | None:
    try:
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            return r.json()
        st.warning(f"GitHub 데이터 조회 실패 ({r.status_code}): {url}")
    except Exception as e:
        st.warning(f"네트워크 오류: {e}")
    return None


def _check_github_url_configured() -> bool:
    """GitHub URL이 기본값(YOUR_GITHUB_USERNAME)으로 남아 있으면 안내 배너 표시"""
    if "YOUR_GITHUB_USERNAME" in GITHUB_RAW_BASE:
        st.error(
            "⚙️ **설정 필요**: `tabs/tab_vm_status.py`의 `GITHUB_RAW_BASE` 변수를 "
            "실제 GitHub 사용자명과 리포지토리명으로 수정해 주세요.",
            icon="🚨",
        )
        with st.expander("수정 방법"):
            st.code(
                'GITHUB_RAW_BASE = (\n'
                '    "https://raw.githubusercontent.com/"\n'
                '    "실제사용자명/실제리포명/main/data"\n'
                ')',
                language="python",
            )
        return False
    return True


def render():
    st.header("🖥️ VM 현황 (실시간 연동)")
    st.caption("VM에서 GitHub에 커밋된 JSON 파일을 읽어 표시합니다. 로컬 PC 상태와 무관합니다.")

    if not _check_github_url_configured():
        return

    col_refresh, col_info = st.columns([1, 5])
    with col_refresh:
        if st.button("🔄 새로고침"):
            st.rerun()
    with col_info:
        st.info("4시간마다 GitHub Actions가 자동 업데이트합니다.")

    st.divider()

    # ── 신호 상태 ──────────────────────────────────────────────────────────
    signal_data = _fetch(URLS["signal"])
    st.subheader("📊 현재 전략 신호")
    if signal_data:
        sig   = signal_data.get("signal", "?")
        emoji = SIGNAL_COLORS.get(sig, "❓")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("신호",     f"{emoji} {sig}")
        c2.metric("현재가",   f"{signal_data.get('current_price', 0):,.0f} 원")
        c3.metric(f"SMA29",   f"{signal_data.get('sma', 0):,.0f} 원")
        c4.metric("업데이트", signal_data.get("updated_at", "-"))

        with st.expander("📐 지표 상세"):
            st.json({
                "Donchian 상단 (115, 4H)": signal_data.get("donchian_upper"),
                "Donchian 하단 (105, 4H)": signal_data.get("donchian_lower"),
                f"SMA {29} (1D)":          signal_data.get("sma"),
                "판단 근거":               signal_data.get("reason"),
            })
    else:
        st.warning("신호 데이터를 가져올 수 없습니다.")

    st.divider()

    # ── 잔고 ───────────────────────────────────────────────────────────────
    balance_data = _fetch(URLS["balance"])
    st.subheader("💰 잔고 현황")
    if balance_data:
        dry = "🧪 (DRY RUN)" if balance_data.get("dry_run") else ""
        st.caption(f"업데이트: {balance_data.get('updated_at', '-')} {dry}")
        balances = balance_data.get("balances", [])
        if isinstance(balances, list):
            rows = []
            for b in balances:
                cur = b.get("currency", "")
                bal = float(b.get("balance", 0))
                locked = float(b.get("locked", 0))
                avg = float(b.get("avg_buy_price", 0))
                if bal + locked > 0:
                    rows.append({
                        "통화": cur,
                        "보유량": f"{bal:.8f}".rstrip("0").rstrip("."),
                        "주문중": f"{locked:.8f}".rstrip("0").rstrip(".") if locked else "-",
                        "평균 매수가": f"{avg:,.0f}" if avg else "-",
                    })
            if rows:
                st.table(rows)
            else:
                st.info("보유 자산 없음")
        else:
            st.json(balances)
    else:
        st.warning("잔고 데이터를 가져올 수 없습니다.")

    st.divider()

    # ── 거래 로그 ──────────────────────────────────────────────────────────
    trade_log = _fetch(URLS["trade_log"])
    st.subheader("📋 실행 로그 (최근 50건)")
    if trade_log and isinstance(trade_log, list):
        display_log = trade_log[:50]
        for entry in display_log:
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
        st.info("거래 로그가 없습니다. GitHub Actions를 실행하면 여기에 기록됩니다.")
