"""
Tab: Reserve Orders (VM 이관 버전)

예약주문은 data/reserve_orders.json에 영구 저장됩니다.
실제 주문 실행은 VM cron (1분마다 vm_trader.py --mode reserve) 에서 담당합니다.
이 탭은 예약 등록 / 조회 / 취소만 담당합니다.
"""
import fcntl
import json
import streamlit as st
from datetime import datetime, date, time
from pathlib import Path
from tabs.tab_log import add_log
from utils import get_ticker_display, is_stock

TICKERS    = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-ADA", "KRW-DOGE"]
STRATEGIES = ["시간 지정 실행", "목표가 돌파 시 매수", "이평선 상향 돌파 시 매수", "리밸런싱 (비율)"]

_DATA_PATH = Path(__file__).parent.parent / "data" / "reserve_orders.json"
_LOCK_PATH = Path(__file__).parent.parent / "data" / "reserve_orders.lock"


def _load_orders() -> list:
    if not _DATA_PATH.exists():
        return []
    try:
        with open(_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_orders(orders: list):
    _DATA_PATH.parent.mkdir(exist_ok=True)
    lock_fp = open(_LOCK_PATH, "w")
    try:
        fcntl.flock(lock_fp, fcntl.LOCK_EX)   # 블로킹 락 (VM cron이 끝날 때까지 대기)
        with open(_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(orders, f, ensure_ascii=False, indent=2)
    finally:
        fcntl.flock(lock_fp, fcntl.LOCK_UN)
        lock_fp.close()


def _datetime_picker(key_prefix: str):
    now = datetime.now()
    col_d, col_h, col_m = st.columns([3, 1, 1])
    with col_d:
        exec_date = st.date_input("실행 날짜", value=now.date(),
                                  min_value=now.date(), key=f"{key_prefix}_date")
    with col_h:
        exec_hour = st.number_input("시", 0, 23, now.hour, step=1, key=f"{key_prefix}_hour")
    with col_m:
        exec_min  = st.number_input("분", 0, 59, now.minute, step=5, key=f"{key_prefix}_min")
    exec_dt = datetime.combine(exec_date, time(int(exec_hour), int(exec_min)))
    st.caption(f"⏰ 실행 예정: **{exec_dt.strftime('%Y-%m-%d %H:%M')}**")
    return exec_dt


def render(broker):
    st.subheader("📅 예약 주문")
    st.caption("VM cron(1분마다)이 조건 도달 시 자동 실행합니다. Streamlit을 닫아도 동작합니다.")

    tab_add, tab_list = st.tabs(["➕ 예약 추가", "📋 예약 목록"])

    # ── 예약 추가 ────────────────────────────────────────────────────────
    with tab_add:
        active_tickers = st.session_state.get("TICKERS", TICKERS)
        c1, c2 = st.columns(2)

        with c1:
            res_ticker     = st.selectbox("종목", active_tickers, key="res_ticker",
                                          format_func=get_ticker_display)
            _is_stock      = is_stock(res_ticker)
            res_side       = st.radio("방향", ["매수", "매도"], horizontal=True, key="res_side")
            res_order_type = st.radio("주문 유형", ["시장가", "지정가"], horizontal=True, key="res_order_type")
            res_strategy   = st.selectbox("전략 유형", STRATEGIES, key="res_strategy")

            res_limit_price = 0
            if res_order_type == "지정가":
                try:
                    curr = broker.get_current_price(res_ticker) or 0
                except Exception:
                    curr = 0
                res_limit_price = st.number_input(
                    "지정 가격 (KRW)", min_value=1,
                    value=int(curr * 0.98) if curr else 100_000, step=1000,
                    key="res_limit_price",
                )
                if curr:
                    st.caption(f"현재가: {curr:,.0f}원 | 설정가: {res_limit_price:,.0f}원 "
                               f"({(res_limit_price/curr-1)*100:+.2f}%)")

            if res_side == "매수":
                res_amount = st.number_input("주문 금액 (KRW)", min_value=5000,
                                             value=50000, step=1000, key="res_amount")
            else:
                if _is_stock:
                    res_amount = st.number_input("주문 수량 (주)", min_value=0,
                                                 value=1, step=1, key="res_amount_coin")
                else:
                    res_amount = st.number_input("주문 수량 (코인)", min_value=0.0,
                                                 value=0.001, step=0.0001,
                                                 format="%.8f", key="res_amount_coin")

        with c2:
            extra = {}
            if res_strategy == "시간 지정 실행":
                exec_dt  = _datetime_picker("res_ts")
                res_note = f"예약 실행: {exec_dt.strftime('%Y-%m-%d %H:%M')}"

            elif res_strategy == "목표가 돌파 시 매수":
                try:
                    curr = broker.get_current_price(res_ticker) or 100_000_000
                except Exception:
                    curr = 100_000_000
                res_target = st.number_input("목표가 (KRW)", min_value=1,
                                             value=int(curr * 1.05), step=1000, key="res_target")
                st.caption(f"현재가: **{curr:,.0f}원** | 목표: **{res_target:,.0f}원**")
                st.markdown("**조건 만료 시각** (이 시각까지 미달성시 취소)")
                exec_dt  = _datetime_picker("res_tgt_exp")
                res_note = f"목표가 {res_target:,}원 돌파 시 (만료: {exec_dt.strftime('%Y-%m-%d %H:%M')})"
                extra["target_price"] = res_target

            elif res_strategy == "이평선 상향 돌파 시 매수":
                res_ma = st.number_input("이동평균 기간 (일)", min_value=1, value=20, key="res_ma")
                st.markdown("**조건 확인 시각**")
                exec_dt  = _datetime_picker("res_ma_ts")
                res_note = f"MA{res_ma} 상향 돌파 시 (확인: {exec_dt.strftime('%Y-%m-%d %H:%M')})"
                extra["ma_period"] = res_ma

            elif res_strategy == "리밸런싱 (비율)":
                res_ratio = st.slider("코인 비율 (%)", 0, 100, 50, key="res_ratio")
                st.markdown("**리밸런싱 실행 시각**")
                exec_dt  = _datetime_picker("res_reb_ts")
                res_note = f"코인 {res_ratio}% 비율 유지 (실행: {exec_dt.strftime('%Y-%m-%d %H:%M')})"
                extra["rebalance_ratio"] = res_ratio

            res_active = st.toggle("활성화", value=True, key="res_active")

        st.divider()
        if st.button("📌 예약 등록", type="primary", key="res_submit"):
            orders = _load_orders()
            order = {
                "id":          len(orders) + 1,
                "created":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "exec_at":     exec_dt.strftime("%Y-%m-%d %H:%M"),
                "ticker":      res_ticker,
                "side":        res_side,
                "order_type":  res_order_type,
                "limit_price": res_limit_price,
                "strategy":    res_strategy,
                "amount":      res_amount,
                "note":        res_note,
                "active":      res_active,
                "status":      "대기중",
                **extra,
            }
            orders.append(order)
            _save_orders(orders)
            type_label = f"지정가({res_limit_price:,}원)" if res_order_type == "지정가" else "시장가"
            add_log(f"[예약등록] {res_ticker} {res_side} {type_label} / {res_note}", "INFO")
            st.success(f"✅ 예약 등록 완료 | {res_ticker} {res_side} [{type_label}] — {exec_dt.strftime('%Y-%m-%d %H:%M')}")

    # ── 예약 목록 ─────────────────────────────────────────────────────────
    with tab_list:
        if st.button("🔄 새로고침", key="res_refresh"):
            st.rerun()

        orders = _load_orders()
        if not orders:
            st.info("등록된 예약 주문이 없습니다.")
        else:
            for i, o in enumerate(orders):
                active_icon = "🟢" if o.get("active") else "⚫"
                status_icon = {"대기중": "⏳", "완료": "✅", "취소": "❌", "실패": "🔴"}.get(o.get("status", ""), "")
                with st.expander(
                    f"{active_icon} [{o['id']}] {get_ticker_display(o['ticker'])} {o['side']}"
                    f" ⏰{o.get('exec_at','?')} — {status_icon} {o.get('status','')}"
                ):
                    col_i1, col_i2 = st.columns(2)
                    with col_i1:
                        st.write(f"- **종목**: {get_ticker_display(o['ticker'])}")
                        st.write(f"- **방향**: {o['side']}")
                        st.write(f"- **전략**: {o['strategy']}")
                        st.write(f"- **실행 시각**: {o.get('exec_at', '—')}")
                    with col_i2:
                        st.write(f"- **조건**: {o['note']}")
                        st.write(f"- **수량/금액**: {o['amount']}")
                        st.write(f"- **등록**: {o['created']}")
                        st.write(f"- **상태**: {o.get('status','')} {o.get('result','')}")
                        if o.get("executed_at"):
                            st.write(f"- **실행 시각**: {o['executed_at']}")

                    bc1, bc2 = st.columns(2)
                    with bc1:
                        toggle_label = "비활성화" if o.get("active") else "활성화"
                        if st.button(toggle_label, key=f"res_tog_{i}"):
                            orders[i]["active"] = not o.get("active")
                            _save_orders(orders)
                            add_log(f"[예약주문] #{o['id']} {toggle_label}", "INFO")
                            st.rerun()
                    with bc2:
                        if st.button("🗑 삭제", key=f"res_del_{i}"):
                            del orders[i]
                            _save_orders(orders)
                            add_log(f"[예약주문] #{o['id']} 삭제", "INFO")
                            st.rerun()
