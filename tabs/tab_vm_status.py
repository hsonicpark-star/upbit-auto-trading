"""
VM 현황 탭 – VM 로컬 파일 읽기 전용

VM에서 실행되는 Streamlit이므로 data/*.json 파일을 직접 읽습니다.
vm_trader.py가 4시간마다 cron으로 실행되어 파일을 업데이트합니다.
"""
import json
import os
from datetime import datetime, timezone, timedelta
import streamlit as st

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
LOG_DIR  = os.path.join(os.path.dirname(__file__), '..')

KST = timezone(timedelta(hours=9))

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


def _parse_kst(ts_str: str) -> datetime | None:
    """'2026-03-28 15:54:47 KST' → datetime(KST)"""
    try:
        return datetime.strptime(ts_str.replace(" KST", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
    except Exception:
        return None


def _age_minutes(ts_str: str) -> int | None:
    """updated_at 문자열로부터 경과 분 반환."""
    dt = _parse_kst(ts_str)
    if dt is None:
        return None
    return int((datetime.now(KST) - dt).total_seconds() / 60)


def _freshness_badge(minutes: int | None) -> str:
    if minutes is None:
        return "❓ 알 수 없음"
    if minutes < 5 * 60:            # 5시간 미만
        return f"✅ 정상 ({minutes // 60}시간 {minutes % 60}분 전)"
    elif minutes < 9 * 60:          # 9시간 미만
        return f"⚠️ 지연 ({minutes // 60}시간 {minutes % 60}분 전)"
    else:
        return f"🔴 비정상 ({minutes // 60}시간 {minutes % 60}분 전 — cron 확인 필요)"


def _cron_health() -> str:
    """reserve.log 마지막 라인 시간으로 cron 헬스 체크."""
    log_path = os.path.join(LOG_DIR, "reserve.log")
    if not os.path.exists(log_path):
        return "❓ reserve.log 없음"
    try:
        with open(log_path, encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        if not lines:
            return "❓ 로그 비어있음"
        last = lines[-1]
        # 형식: "2026-03-28 07:22:02 [INFO] ..."
        ts_str = last[:19]
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
        elapsed = int((datetime.now(KST) - dt).total_seconds() / 60)
        if elapsed <= 2:
            return f"✅ 정상 (1분 전)"
        elif elapsed <= 5:
            return f"⚠️ {elapsed}분 전 마지막 실행"
        else:
            return f"🔴 {elapsed}분째 미실행 — cron 점검 필요"
    except Exception as e:
        return f"❓ 확인 실패: {e}"


def render():
    st.header("🖥️ VM 현황 (실시간 연동)")

    col_refresh, _ = st.columns([1, 5])
    with col_refresh:
        if st.button("🔄 새로고침"):
            st.rerun()

    # ── VM 상태 요약 배너 ────────────────────────────────────────────────
    st.subheader("🩺 VM 상태 요약")
    signal_data = _load("signal_state.json")

    updated_at = signal_data.get("updated_at", "") if signal_data else ""
    age_min    = _age_minutes(updated_at)
    freshness  = _freshness_badge(age_min)
    cron_ok    = _cron_health()

    # 다음 auto 실행 예정
    next_run_str = "—"
    if updated_at:
        last_dt = _parse_kst(updated_at)
        if last_dt:
            next_dt     = last_dt + timedelta(hours=4)
            next_run_str = next_dt.strftime("%m/%d %H:%M")

    b1, b2, b3 = st.columns(3)
    b1.metric("전략 데이터",    freshness)
    b2.metric("cron(1분) 상태", cron_ok)
    b3.metric("다음 auto 실행", next_run_str)

    st.divider()

    # ── 신호 상태 ──────────────────────────────────────────────────────────
    st.subheader("📊 현재 전략 신호")
    if signal_data:
        sig   = signal_data.get("signal", "?")
        emoji = SIGNAL_COLORS.get(sig, "❓")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("신호",     f"{emoji} {sig}")
        c2.metric("현재가",   f"{signal_data.get('current_price', 0):,.0f} 원")
        c3.metric("SMA29",    f"{signal_data.get('sma', 0):,.0f} 원")
        c4.metric("업데이트", signal_data.get("updated_at", "-"))

        # ── 수익률 표시 (BTC 보유 중일 때) ────────────────────────────────
        profit_pct = signal_data.get("profit_pct")
        avg_buy    = signal_data.get("avg_buy_price")
        holding    = signal_data.get("holding_btc")
        if profit_pct is not None and avg_buy:
            st.divider()
            p1, p2, p3 = st.columns(3)
            color = "normal" if profit_pct >= 0 else "inverse"
            p1.metric("평균 매수가",  f"{avg_buy:,.0f} 원")
            p2.metric("현재 수익률",  f"{profit_pct:+.2f} %",
                      delta=f"{profit_pct:+.2f}%", delta_color=color)
            p3.metric("BTC 보유량",   f"{holding:.6f}" if holding else "-")

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
                        "통화":        cur,
                        "보유량":      f"{bal:.8f}".rstrip("0").rstrip("."),
                        "주문중":      f"{locked:.8f}".rstrip("0").rstrip(".") if locked > 0 else "-",
                        "평균 매수가": f"{avg:,.0f}" if avg else "-",
                    })
            if rows:
                import pandas as pd
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
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

    # CSV 다운로드
    csv_path = os.path.join(DATA_DIR, "trade_log.csv")
    if os.path.exists(csv_path):
        with open(csv_path, encoding="utf-8-sig") as f:
            csv_bytes = f.read().encode("utf-8-sig")
        st.download_button("⬇️ CSV 다운로드", data=csv_bytes,
                           file_name="trade_log.csv", mime="text/csv",
                           key="dl_trade_csv")

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
                st.write(f"`{t}` {color} **{side} 주문** {dry} | 가격: {price:,.0f}원"
                         if price else f"`{t}` {color} **{side} 주문** {dry}")
            elif etype == "MANUAL":
                side = "매수" if entry.get("side") == "buy" else "매도"
                st.write(f"`{t}` 🔧 **수동 {side}** | {entry.get('ticker','')} {dry}")
            elif etype == "RESERVE":
                order  = entry.get("order", {})
                status = order.get("status", "")
                color  = "🟢" if status == "OK" else "🔴"
                st.write(f"`{t}` {color} **예약주문** | {signal} | {order.get('detail','')}")
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
