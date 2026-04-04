"""
Tab: Trading History
Shows completed trades, deposits, and withdrawals via broker interface.
"""
import streamlit as st
import pandas as pd
from pathlib import Path
from tabs.tab_log import add_log
from utils import get_ticker_display, is_stock

_CSV_PATH = Path(__file__).parent.parent / "data" / "trade_log.csv"

TICKERS = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-ADA", "KRW-DOGE"]


def _load_profit_stats() -> dict | None:
    """trade_log.csv에서 수익률 통계 계산 (ORDER 타입, OK 상태만)."""
    if not _CSV_PATH.exists():
        return None
    try:
        df = pd.read_csv(_CSV_PATH, encoding="utf-8-sig")
        orders = df[(df["type"] == "ORDER") & (df["order_status"] == "OK")].copy()
        orders["profit_pct"] = pd.to_numeric(orders["profit_pct"], errors="coerce")
        profits = orders["profit_pct"].dropna()
        if profits.empty:
            return {"count": len(orders), "profit_count": 0, "win_rate": None,
                    "avg_profit": None, "max_profit": None, "max_loss": None}
        wins = profits[profits > 0]
        losses = profits[profits < 0]
        return {
            "count":       len(profits),
            "win_rate":    round(len(wins) / len(profits) * 100, 1),
            "avg_profit":  round(profits.mean(), 2),
            "avg_win":     round(wins.mean(), 2) if not wins.empty else 0,
            "avg_loss":    round(losses.mean(), 2) if not losses.empty else 0,
            "max_profit":  round(profits.max(), 2),
            "max_loss":    round(profits.min(), 2),
        }
    except Exception:
        return None


def _fetch_orders(broker, ticker, state="done", count=50):
    """Fetch orders with given state: done / cancel / wait."""
    try:
        result = broker.get_order(ticker, state=state)
        return result if result else []
    except Exception as e:
        add_log(f"[거래내역 오류] {e}", "ERROR")
        return []


def _orders_to_df(orders, ticker=None):
    """Convert order list to display DataFrame."""
    if not orders:
        return pd.DataFrame()
    _is_stock = is_stock(ticker) if ticker else False
    rows = []
    for o in orders:
        if not isinstance(o, dict):
            continue
        side = "매수" if o.get("side") == "bid" else "매도"
        price = float(o.get("price") or 0)
        vol = float(o.get("executed_volume") or o.get("volume") or 0)
        fee = float(o.get("paid_fee") or 0)
        total = price * vol
        qty_fmt = f"{vol:,.0f}" if _is_stock else f"{vol:.8f}"
        rows.append({
            "시각":   o.get("created_at", "")[:19],
            "방향":   side,
            "종목":   get_ticker_display(o.get("market", "")),
            "가격 (KRW)":  f"{price:,.0f}",
            "수량":    qty_fmt,
            "총액 (KRW)":  f"{total:,.0f}",
            "수수료":  f"{fee:.4f}" if fee else "—",
            "상태":   o.get("state", ""),
        })
    return pd.DataFrame(rows)


def render(broker):
    broker_name = getattr(broker, "name", "브로커")
    st.subheader(f"📂 거래 내역 — {broker_name}")

    # ── 수익률 통계 (trade_log.csv 기반) ─────────────────────────────────
    stats = _load_profit_stats()
    if stats and stats.get("count", 0) > 0:
        st.subheader("📊 자동매매 수익률 통계")
        s1, s2, s3, s4, s5 = st.columns(5)
        s1.metric("총 체결 횟수",  f"{stats['count']}건")
        s2.metric("승률",          f"{stats['win_rate']} %" if stats['win_rate'] is not None else "—")
        s3.metric("평균 수익률",   f"{stats['avg_profit']:+.2f} %" if stats['avg_profit'] is not None else "—")
        s4.metric("최대 수익",     f"{stats['max_profit']:+.2f} %" if stats['max_profit'] is not None else "—")
        s5.metric("최대 손실",     f"{stats['max_loss']:+.2f} %" if stats['max_loss'] is not None else "—")
        with st.expander("상세 통계"):
            st.write(f"- 평균 수익 거래: **{stats.get('avg_win', 0):+.2f} %**")
            st.write(f"- 평균 손실 거래: **{stats.get('avg_loss', 0):+.2f} %**")
        st.divider()

    hist_tab1, hist_tab2, hist_tab3 = st.tabs(["💹 체결 내역", "📥 입금 내역", "📤 출금 내역"])

    # ── 체결 내역 ─────────────────────────────────────────────────────
    with hist_tab1:
        st.caption("완료된 매수/매도 체결 내역을 조회합니다.")
        active_tickers = st.session_state.get("TICKERS", TICKERS)
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            hist_ticker = st.selectbox("마켓/종목 선택", active_tickers, key="hist_ticker",
                                      format_func=get_ticker_display)
        with col2:
            hist_state = st.radio("상태", ["체결", "취소"], horizontal=True, key="hist_state")
        with col3:
            st.write("")
            if st.button("🔄 조회", key="hist_refresh"):
                st.rerun()

        state_map = {"체결": "done", "취소": "cancel"}
        orders = _fetch_orders(broker, hist_ticker, state=state_map[hist_state])
        df = _orders_to_df(orders, hist_ticker)

        if df.empty:
            st.info("조회된 내역이 없습니다.")
        else:
            done_orders = [o for o in orders if isinstance(o, dict) and o.get("side") == "bid"]
            sell_orders = [o for o in orders if isinstance(o, dict) and o.get("side") == "ask"]
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("전체 주문 수", len(orders))
            mc2.metric("매수 주문", len(done_orders))
            mc3.metric("매도 주문", len(sell_orders))
            st.divider()
            st.dataframe(df, use_container_width=True, hide_index=True)

    # ── 입금 내역 ─────────────────────────────────────────────────────
    with hist_tab2:
        st.caption("KRW 입금 내역을 조회합니다.")
        if st.button("🔄 입금 내역 조회", key="dep_refresh"):
            st.rerun()
        try:
            if hasattr(broker, "get_deposit_history"):
                dep_list = broker.get_deposit_history("KRW", count=20)
                if dep_list:
                    rows = []
                    for d in dep_list:
                        rows.append({
                            "시각": d.get("created_at", d.get("done_at", ""))[:19],
                            "유형": "KRW 입금",
                            "금액": f"{float(d.get('amount', 0)):,.0f}원",
                            "상태": d.get("state", ""),
                            "거래 ID": str(d.get("txid", ""))[:20],
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                else:
                    st.info("입금 내역이 없습니다.")
            else:
                st.info(f"{broker_name}은(는) 입금 내역 조회를 지원하지 않습니다.")
        except Exception as e:
            st.warning(f"입금 내역 조회 실패: {e}")

    # ── 출금 내역 ─────────────────────────────────────────────────────
    with hist_tab3:
        st.caption("KRW 출금 내역을 조회합니다.")
        if st.button("🔄 출금 내역 조회", key="wd_refresh"):
            st.rerun()
        try:
            if hasattr(broker, "get_withdraw_history"):
                wd_list = broker.get_withdraw_history("KRW", count=20)
                if wd_list:
                    rows = []
                    for w in wd_list:
                        rows.append({
                            "시각": w.get("created_at", w.get("done_at", ""))[:19],
                            "유형": "KRW 출금",
                            "금액": f"{float(w.get('amount', 0)):,.0f}원",
                            "상태": w.get("state", ""),
                            "거래 ID": str(w.get("txid", ""))[:20],
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                else:
                    st.info("출금 내역이 없습니다.")
            else:
                st.info(f"{broker_name}은(는) 출금 내역 조회를 지원하지 않습니다.")
        except Exception as e:
            st.warning(f"출금 내역 조회 실패: {e}")
