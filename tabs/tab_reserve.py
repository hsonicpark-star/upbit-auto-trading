"""
Tab: Reserve Orders
Schedule orders by time or strategy condition.
Execution time is fully user-configurable: date + hour + minute.
"""
import streamlit as st
import pandas as pd
from datetime import datetime, date, time, timedelta
from streamlit_autorefresh import st_autorefresh
from tabs.tab_log import add_log
from utils import get_ticker_display, is_stock

TICKERS = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-ADA", "KRW-DOGE"]
STRATEGIES = ["시간 지정 실행", "목표가 돌파 시 매수", "이평선 상향 돌파 시 매수", "리밸런싱 (비율)"]

def _init():
    if "reserve_orders" not in st.session_state:
        st.session_state.reserve_orders = []

def _execute_order(broker, order: dict) -> tuple[bool, str]:
    """
    Execute a single reserve order via pyupbit API.
    Returns (success: bool, message: str)
    """
    ticker      = order["ticker"]
    side        = order["side"]
    order_type  = order.get("order_type", "시장가")
    limit_price = float(order.get("limit_price") or 0)
    amount      = float(order["amount"])
    try:
        result = None
        if side == "매수":
            if order_type == "지정가" and limit_price > 0:
                qty    = amount / limit_price
                result = broker.buy_limit_order(ticker, limit_price, qty)
                label  = f"✅ 지정가매수 {ticker} {limit_price:,.0f}원×{qty:.6f}"
            else:
                result = broker.buy_market_order(ticker, amount)
                label  = f"✅ 시장가매수 {ticker} {amount:,.0f}원"
        else:  # 매도
            if order_type == "지정가" and limit_price > 0:
                result = broker.sell_limit_order(ticker, limit_price, amount)
                label  = f"✅ 지정가매도 {ticker} {limit_price:,.0f}원×{amount:.6f}"
            else:
                result = broker.sell_market_order(ticker, amount)
                label  = f"✅ 시장가매도 {ticker} {amount:.6f}"

        if result is None:
            msg = f"❌ 주문 거부 (잔고 부족 또는 최소금액 미달)"
            return False, msg
        uuid = result.get("uuid", "") if isinstance(result, dict) else ""
        return True, f"{label} | uuid={uuid[:8]}" if uuid else label
    except Exception as e:
        return False, f"❌ 실행 오류: {e}"


def _check_and_execute(broker):
    """
    Scan all active 'wait' orders whose exec_at <= now and execute them.
    Only handles '\uc2dc\uac04 \uc9c0\uc815 \uc2e4\ud589' strategy for now.
    Condition-based strategies (\ub9e4\uc218/\uc774\ud3c9\uc120/\ub9ac\ubc38\ub7f0\uc2f1) require separate price-check logic.
    """
    if "reserve_orders" not in st.session_state:
        return
    now = datetime.now()
    changed = False
    for i, order in enumerate(st.session_state.reserve_orders):
        if not order.get("active") or order.get("status") != "대기중":
            continue
        exec_at_str = order.get("exec_at", "")
        if not exec_at_str:
            continue
        try:
            exec_dt = datetime.strptime(exec_at_str, "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        # Fire if execution time has arrived
        if now >= exec_dt:
            strategy = order.get("strategy", "")
            if strategy == "시간 지정 실행":
                success, msg = _execute_order(broker, order)
                st.session_state.reserve_orders[i]["status"] = "완료" if success else "실패"
                st.session_state.reserve_orders[i]["result"]  = msg
                level = "ORDER" if success else "ERROR"
                add_log(f"[예약실행] #{order['id']} {msg}", level)
                changed = True
            # TODO: condition-based strategies (price/MA check) to be added
    return changed


def _datetime_picker(key_prefix: str):
    """
    Custom date+time picker using st.date_input + two number_inputs (hour, minute).
    Returns a datetime object.
    """
    now = datetime.now()
    col_d, col_h, col_m = st.columns([3, 1, 1])
    with col_d:
        exec_date = st.date_input(
            "실행 날짜",
            value=now.date(),
            min_value=now.date(),
            key=f"{key_prefix}_date",
        )
    with col_h:
        exec_hour = st.number_input(
            "시",
            min_value=0, max_value=23,
            value=now.hour,
            step=1,
            key=f"{key_prefix}_hour",
        )
    with col_m:
        exec_min = st.number_input(
            "분",
            min_value=0, max_value=59,
            value=now.minute,
            step=5,
            key=f"{key_prefix}_min",
        )
    exec_dt = datetime.combine(exec_date, time(int(exec_hour), int(exec_min)))
    st.caption(f"⏰ 실행 예정: **{exec_dt.strftime('%Y-%m-%d %H:%M')}**")
    return exec_dt


def render(broker):
    _init()
    
    # 30초마다 자동 갱신하여 시간이 된 주문이 있는지 체크
    st_autorefresh(interval=30_000, key="reserve_autorefresh")
    
    # 시간에 도달한 주문 실행
    if _check_and_execute(broker):
        st.rerun(scope="fragment")

    st.subheader("📅 예약 주문")
    st.caption("시간 또는 전략 조건에 따라 자동으로 실행될 주문을 예약합니다.")

    tab_add, tab_list = st.tabs(["➕ 예약 추가", "📋 예약 목록"])

    # ── 예약 추가 폼 ──────────────────────────────────────────────────
    with tab_add:
        active_tickers = st.session_state.get("TICKERS", TICKERS)
        c1, c2 = st.columns(2)
        with c1:
            res_ticker   = st.selectbox("종목", active_tickers, key="res_ticker",
                                        format_func=get_ticker_display)
            _is_stock = is_stock(res_ticker)
            res_side     = st.radio("방향", ["매수", "매도"], horizontal=True, key="res_side")
            res_order_type = st.radio("주문 유형", ["시장가", "지정가"], horizontal=True, key="res_order_type")
            res_strategy = st.selectbox("전략 유형", STRATEGIES, key="res_strategy")

            # 지정가 선택 시 가격 입력
            if res_order_type == "지정가":
                try:
                    curr = broker.get_current_price(res_ticker) or 0
                except Exception:
                    curr = 0
                res_limit_price = st.number_input(
                    "지정 가격 (KRW)" if _is_stock else "지정 가격 (KRW/코인)",
                    min_value=1,
                    value=int(curr * 0.98) if curr else 100_000,
                    step=1000,
                    key="res_limit_price",
                    help="지정가 매수: 현재가보다 낮게 / 매도: 현재가보다 높게 설정",
                )
                if curr:
                    st.caption(f"현재가: {curr:,.0f}원 | 설정가: {res_limit_price:,.0f}원 ({(res_limit_price/curr-1)*100:+.2f}%)")
            else:
                res_limit_price = 0

            if res_side == "매수":
                res_amount = st.number_input(
                    "주문 금액 (KRW)", min_value=5000, value=50000, step=1000, key="res_amount"
                )
            else:
                if _is_stock:
                    res_amount = st.number_input(
                        "주문 수량 (주)", min_value=0, value=1,
                        step=1, key="res_amount_coin"
                    )
                else:
                    res_amount = st.number_input(
                        "주문 수량 (코인)", min_value=0.0, value=0.001,
                        step=0.0001, format="%.8f", key="res_amount_coin"
                    )

        with c2:
            # ── 전략별 조건 입력 ────────────────────────────────────
            if res_strategy == "시간 지정 실행":
                exec_dt  = _datetime_picker("res_ts")
                res_note = f"예약 실행: {exec_dt.strftime('%Y-%m-%d %H:%M')}"

            elif res_strategy == "목표가 돌파 시 매수":
                try:
                    curr = broker.get_current_price(res_ticker) or 100_000_000
                except Exception:
                    curr = 100_000_000
                res_target = st.number_input(
                    "목표가 (KRW)", min_value=1, value=int(curr * 1.05),
                    step=1000, key="res_target",
                    help="현재가보다 높게 설정하면 돌파 매수"
                )
                st.caption(f"현재가: **{curr:,.0f}원** | 목표: **{res_target:,.0f}원**")
                # 만료 시각 선택 (선택적)
                st.markdown("**조건 만료 시각** (이 시각까지 미달성시 취소)")
                exec_dt  = _datetime_picker("res_tgt_exp")
                res_note = f"목표가 {res_target:,}원 돌파 시 (만료: {exec_dt.strftime('%Y-%m-%d %H:%M')})"

            elif res_strategy == "이평선 상향 돌파 시 매수":
                res_ma = st.number_input(
                    "이동평균 기간 (일)", min_value=1, value=20, key="res_ma"
                )
                st.markdown("**조건 확인 시각**")
                exec_dt  = _datetime_picker("res_ma_ts")
                res_note = f"MA{res_ma} 상향 돌파 시 (확인: {exec_dt.strftime('%Y-%m-%d %H:%M')})"

            elif res_strategy == "리밸런싱 (비율)":
                res_ratio = st.slider(
                    "코인 비율 (%)", 0, 100, 50, key="res_ratio",
                    help="총 자산 대비 코인 보유 비율 목표"
                )
                st.markdown("**리밸런싱 실행 시각**")
                exec_dt  = _datetime_picker("res_reb_ts")
                res_note = f"코인 {res_ratio}% 비율 유지 (실행: {exec_dt.strftime('%Y-%m-%d %H:%M')})"

            res_active = st.toggle("활성화", value=True, key="res_active")

        st.divider()
        if st.button("📌 예약 등록", type="primary", key="res_submit"):
            order = {
                "id":          len(st.session_state.reserve_orders) + 1,
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
            }
            type_label = f"지정가({res_limit_price:,}원)" if res_order_type == "지정가" else "시장가"
            st.session_state.reserve_orders.append(order)
            add_log(f"[예약등록] {res_ticker} {res_side} {type_label} / {res_note}", "INFO")
            st.success(f"✅ 예약 주문 등록: {res_ticker} {res_side} [{type_label}] — {exec_dt.strftime('%Y-%m-%d %H:%M')}")

    # ── 예약 목록 ──────────────────────────────────────────────────────
    with tab_list:
        orders = st.session_state.reserve_orders
        if not orders:
            st.info("등록된 예약 주문이 없습니다.")
        else:
            for i, o in enumerate(orders):
                active_icon = "🟢" if o["active"] else "⚫"
                status_icon = {"대기중": "⏳", "완료": "✅", "취소": "❌"}.get(o["status"], "")
                with st.expander(
                    f"{active_icon} [{o['id']}] {get_ticker_display(o['ticker'])} {o['side']}"
                    f" ⏰{o.get('exec_at','?')} — {status_icon} {o['status']}"
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
                        st.write(f"- **상태**: {o['status']}")

                    bc1, bc2, bc3 = st.columns(3)
                    with bc1:
                        toggle_label = "비활성화" if o["active"] else "활성화"
                        if st.button(toggle_label, key=f"res_tog_{i}"):
                            st.session_state.reserve_orders[i]["active"] = not o["active"]
                            add_log(f"[예약주문] #{o['id']} {toggle_label}", "INFO")
                            st.rerun(scope="fragment")
                    with bc2:
                        if st.button("🗑 삭제", key=f"res_del_{i}"):
                            del st.session_state.reserve_orders[i]
                            add_log(f"[예약주문] #{o['id']} 삭제", "INFO")
                            st.rerun(scope="fragment")
                    with bc3:
                        if st.button("✅ 완료 처리", key=f"res_done_{i}"):
                            st.session_state.reserve_orders[i]["status"] = "완료"
                            add_log(f"[예약주문] #{o['id']} 완료", "ORDER")
                            st.rerun(scope="fragment")
