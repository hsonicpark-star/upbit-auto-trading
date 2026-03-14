"""
Tab: Manual Order
Place buy/sell orders manually via pyupbit.
Includes pending order list with cancel button.
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
from tabs.tab_log import add_log
from utils import get_ticker_display, is_stock

TICKERS = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-ADA", "KRW-DOGE"]


def _get_all_pending_orders(broker):
    """Fetch pending (wait) orders across ALL watched tickers."""
    all_orders = []
    
    # st.session_state에 TICKERS가 있으면 그것을 우선 사용
    active_tickers = st.session_state.get("TICKERS", TICKERS)
    
    for t in active_tickers:
        try:
            orders = broker.get_order(t, state="wait")
            if orders:
                all_orders.extend(orders)
        except Exception:
            pass
    return all_orders


def _render_orderbook_html(ob_data):
    if not ob_data or "orderbook_units" not in ob_data:
        st.info("호가 데이터를 수신 중입니다...")
        return

    units = ob_data["orderbook_units"]
    total_ask_size = ob_data.get("total_ask_size", 0)
    total_bid_size = ob_data.get("total_bid_size", 0)

    # 화면에 다 들어오도록 전체 레이아웃 압축 CSS 주입
    st.markdown("""
        <style>
        /* 일반 버튼(호가, 취소 등)의 상하 크기 최소화 */
        div.stButton > button[kind="secondary"] {
            min-height: 22px !important;
            height: 24px !important;
            padding: 0px 4px !important;
            font-size: 13px !important;
        }
        /* 마크다운 텍스트 여백 축소 */
        .stMarkdown p {
            margin-bottom: 0px !important;
            font-size: 13px !important;
        }
        /* 위아래 행 간격 극소화 */
        div[data-testid="stVerticalBlock"] {
            gap: 0.1rem !important;
        }
        div[data-testid="stHorizontalBlock"] {
            gap: 0.1rem !important;
            align-items: center !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # 헤더
    h1, h2, h3 = st.columns([1, 1, 1], gap="small")
    with h1: st.markdown("<div style='text-align:center;'><b>매도잔량</b></div>", unsafe_allow_html=True)
    with h2: st.markdown("<div style='text-align:center;'><b>호가</b></div>", unsafe_allow_html=True)
    with h3: st.markdown("<div style='text-align:center;'><b>매수잔량</b></div>", unsafe_allow_html=True)
    st.divider()

    # 매도 호가 (가까운 7호가)
    ask_units = units[:7]
    for u in reversed(ask_units):
        ap = u['ask_price']
        asz = u['ask_size']
        c1, c2, c3 = st.columns([1, 1, 1], gap="small")
        with c1: st.markdown(f"<div style='text-align:right; color:#ef4444; padding-right:5px;'>{asz:.4f}</div>", unsafe_allow_html=True)
        with c2:
            if st.button(f"{ap:,.0f}", key=f"ask_{ap}", use_container_width=True):
                st.session_state.ord_price = int(ap)
                st.session_state.ord_type = "지정가"
                st.rerun(scope="fragment")
        with c3: st.write("")

    st.markdown("---")

    # 매수 호가 (가까운 7호가 정순)
    bid_units = units[:7]
    for u in bid_units:
        bp = u['bid_price']
        bsz = u['bid_size']
        c1, c2, c3 = st.columns([1, 1, 1], gap="small")
        with c1: st.write("")
        with c2:
            if st.button(f"{bp:,.0f}", key=f"bid_{bp}", use_container_width=True):
                st.session_state.ord_price = int(bp)
                st.session_state.ord_type = "지정가"
                st.rerun(scope="fragment")
        with c3: st.markdown(f"<div style='text-align:left; color:#3b82f6; padding-left:5px;'>{bsz:.4f}</div>", unsafe_allow_html=True)

    st.markdown(f"<div style='display: flex; justify-content: space-between; font-size: 12px; margin-top: 5px; color: gray;'><span>총잔량: {total_ask_size:,.4f}</span><span>총잔량: {total_bid_size:,.4f}</span></div>", unsafe_allow_html=True)


def render(broker, ticker=None):
    active_tickers = st.session_state.get("TICKERS", TICKERS)
    
    if ticker is None or ticker not in active_tickers:
        ticker = active_tickers[0] if active_tickers else "KRW-BTC"

    # 동적으로 웹소켓 매니저 불러오기
    ob_manager = st.session_state.get("ob_manager")

    # 실시간 호가 반응을 위한 1초 리프레시
    st_autorefresh(interval=1000, key="orderbook_refresh")

    st.subheader("🛒 수동 주문")
    st.caption("직접 매수/매도 주문을 넣거나 호가를 확인할 수 있습니다.")

    # ── 현재 잔고 (상단 배치) ───────────────────────────────────────────
    st.markdown("#### 💼 현재 잔고")
    try:
        balances = broker.get_balances()
        rows = []
        for b in balances:
            bal = float(b.get("balance", 0) or 0)
            locked = float(b.get("locked", 0) or 0)
            if bal + locked > 0:
                rows.append({
                    "통화": b["currency"],
                    "보유량": f"{bal:.8f}",
                    "잠금": f"{locked:.8f}",
                })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("보유 자산이 없습니다.")
    except Exception as e:
        st.error(f"잔고 조회 실패: {e}")

    st.divider()

    col_ob, col_order = st.columns([1, 1.2])

    # ── 실시간 호가 (좌측) ──────────────────────────────────────────
    with col_ob:
        st.markdown("#### 📊 실시간 호가 (7호가)")
        ob_data = ob_manager.get_orderbook()
        _render_orderbook_html(ob_data)

    # ── 주문 입력 폼 (우측) ──────────────────────────────────────────────────
    with col_order:
        st.markdown("#### 📝 주문 입력")
        order_ticker = st.selectbox("마켓/종목 선택", active_tickers, key="ord_ticker",
                                    index=active_tickers.index(ticker) if ticker in active_tickers else 0,
                                    format_func=get_ticker_display)
        # 웹소켓 매니저에 구독 요청
        if ob_manager:
            ob_manager.subscribe(order_ticker)

        order_side = st.radio("주문 방향", ["매수", "매도"], horizontal=True, key="ord_side")
        order_type = st.radio("주문 유형", ["시장가", "지정가"], horizontal=True, key="ord_type")

        # Current price
        try:
            curr_price = broker.get_current_price(order_ticker)
            st.info(f"현재가: **{curr_price:,.0f} 원**")
        except Exception:
            curr_price = 0
            st.warning("현재가 조회 실패")

        if order_type == "지정가":
            if "ord_price" not in st.session_state:
                st.session_state.ord_price = int(curr_price * 0.98) if curr_price else 100000

            price = st.number_input("주문 가격 (KRW)", min_value=1,
                                    step=1000, key="ord_price")
        else:
            price = 0

        _is_stock = is_stock(order_ticker)
        _qty_label = "주식 수량 (주)" if _is_stock else "주문 수량 (코인)"

        if order_side == "매수":
            amount_krw = st.number_input(
                "주문 금액 (KRW)", min_value=1000, value=5000, step=1000, key="ord_amount_krw"
            )
        else:
            try:
                coin_bal = broker.get_balance(order_ticker)
            except Exception:
                coin_bal = 0.0
            if _is_stock:
                amount_coin = st.number_input(
                    _qty_label, min_value=0, value=int(coin_bal or 0),
                    step=1, key="ord_amount_coin"
                )
            else:
                amount_coin = st.number_input(
                    _qty_label, min_value=0.0, value=float(coin_bal or 0),
                    step=0.0001, format="%.8f", key="ord_amount_coin"
                )

        st.divider()

        confirmed = st.checkbox("⚠️ 실제 주문 실행에 동의합니다", key="ord_confirm")

        if st.button("🚀 주문 실행", type="primary", key="ord_submit", disabled=not confirmed):
            try:
                result = None
                if order_side == "매수":
                    if order_type == "시장가":
                        result = broker.buy_market_order(order_ticker, amount_krw)
                        label = f"시장가매수 {order_ticker} {amount_krw:,}원"
                    else:
                        qty = amount_krw / price if price > 0 else 0
                        # 주식인 경우 수량이 정수여야 하지만, Broker에서 알아서 처리하도록 하거나 여기서 int 캐스팅
                        if not order_ticker.startswith("KRW-"):
                            qty = int(qty)
                        result = broker.buy_limit_order(order_ticker, price, qty)
                        label = f"지정가매수 {order_ticker} {price:,}원 × {qty:.6f}"
                else:
                    if order_type == "시장가":
                        result = broker.sell_market_order(order_ticker, amount_coin)
                        label = f"시장가매도 {order_ticker} {amount_coin:.8f}"
                    else:
                        result = broker.sell_limit_order(order_ticker, price, amount_coin)
                        label = f"지정가매도 {order_ticker} {price:,}원 × {amount_coin:.8f}"

                if result is None:
                    msg = f"주문 거부됨 — 잔고 부족 또는 최소금액 미달 ({label})"
                    add_log(f"[주문실패] {msg}", "ERROR")
                    st.error(f"❌ {msg}")
                else:
                    uuid = result.get("uuid", "") if isinstance(result, dict) else str(result)
                    add_log(f"[주문성공] {label} | uuid={uuid[:8] if uuid else ''}", "ORDER")
                    st.success(f"✅ 주문 접수: {label}")
                    if uuid:
                        st.caption(f"주문 ID: `{uuid}`")
                    st.rerun(scope="fragment")
            except Exception as e:
                add_log(f"[주문오류] {e}", "ERROR")
                st.error(f"주문 실패: {e}")

    st.divider()

    # ── 미체결 주문 현황 (전체 티커 일괄 조회) ────────────────────────────
    st.markdown("#### 📋 미체결 주문 현황 (전체 종목)")
    col_r1, col_r2 = st.columns([1, 5])
    with col_r1:
        if st.button("🔄 조회", key="pending_refresh"):
            st.rerun(scope="fragment")

    pending = _get_all_pending_orders(broker)

    if not pending:
        st.info("미체결 주문이 없습니다.")
    else:
        st.caption(f"총 {len(pending)}건의 미체결 주문")
        # Table header
        h0, h1, h2, h3, h4, h5, h6, h7 = st.columns([2, 1.5, 1.5, 2, 2, 2, 2, 1.5])
        h0.markdown("**시각**"); h1.markdown("**방향**"); h2.markdown("**종목**")
        h3.markdown("**가격**"); h4.markdown("**총금액(KRW)**"); h5.markdown("**주문수량**"); h6.markdown("**잔여수량**"); h7.markdown("**취소**")
        st.divider()
        for order in pending:
            side_icon = "🟢 매수" if order.get("side") == "bid" else "🔴 매도"
            uuid      = order.get("uuid", "")
            market    = order.get("market", "")
            price_val = float(order.get("price") or 0)
            vol       = float(order.get("volume") or 0)
            rem       = float(order.get("remaining_volume") or 0)
            created   = order.get("created_at", "")[:16]

            total_krw = price_val * vol
            rem_krw   = price_val * rem

            c0, c1, c2, c3, c4, c5, c6, c7 = st.columns([2, 1.5, 1.5, 2, 2, 2, 2, 1.5])
            c0.write(created)
            c1.write(side_icon)
            c2.write(get_ticker_display(market))
            c3.write(f"{price_val:,.0f}원")
            c4.write(f"{total_krw:,.0f}원")
            c5.write(f"{vol:.6f}")
            c6.write(f"{rem:.6f} ({rem_krw:,.0f}원)")
            if c7.button("취소", key=f"cancel_{uuid}"):
                try:
                    broker.cancel_order(uuid)
                    add_log(f"[주문취소] {market} {uuid[:8]}", "ORDER")
                    st.success("주문이 취소되었습니다.")
                    st.rerun(scope="fragment")
                except Exception as e:
                    add_log(f"[취소오류] {e}", "ERROR")
                    st.error(f"취소 실패: {e}")
