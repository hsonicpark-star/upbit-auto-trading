"""
Tab: Monitor
Real-time price monitoring with MA strategy chart and signal table.

Performance:
  - Chart OHLCV data : cached 300s (re-fetched only when new candle forms)
  - MA values        : cached 60s
  - Current price    : cached 10s  ← only lightweight call runs frequently
  - Auto-rerun       : 15s interval, toggleable by user
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
from strategy import get_ohlcv_with_ma, check_ma_signal, get_current_price_cached, INTERVAL_MAP
from tabs.tab_log import add_log
from utils import get_ticker_display, is_stock

ALL_MA_OPTIONS = [5, 10, 20, 60, 120]
MA_COLORS = {5: "#f59e0b", 10: "#3b82f6", 20: "#10b981", 60: "#ec4899", 120: "#a855f7"}
DEFAULT_MA = [5, 10, 20, 60]
DISPLAY_COUNTS = {"day": 90, "minute240": 120}


def _build_chart(df, selected_ma, strategy_ma, interval_label):
    if df is None or df.empty or 'open' not in df.columns:
        return go.Figure()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['open'], high=df['high'],
        low=df['low'], close=df['close'], name="캔들",
        increasing_line_color="#ef4444", decreasing_line_color="#3b82f6",
        increasing_fillcolor="#ef4444", decreasing_fillcolor="#3b82f6",
    ))
    for p in selected_ma:
        col = f"MA{p}"
        if col not in df.columns:
            continue
        is_strategy = (p == strategy_ma)
        fig.add_trace(go.Scatter(
            x=df.index, y=df[col], mode="lines",
            name=f"MA{p}" + (" ★전략" if is_strategy else ""),
            line=dict(color=MA_COLORS.get(p, "#fff"),
                      width=2.5 if is_strategy else 1.5,
                      dash="dash" if is_strategy else "solid"),
        ))
    if strategy_ma not in selected_ma:
        col = f"MA{strategy_ma}"
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col], mode="lines",
                name=f"MA{strategy_ma} ★전략",
                line=dict(color="#ffffff", width=2.5, dash="dot"),
            ))
    fig.update_layout(
        height=460, template="plotly_dark",
        title=dict(text=f"캔들차트 + 이동평균선 [{interval_label}]", font=dict(size=14)),
        xaxis_rangeslider_visible=False,
        margin=dict(l=0, r=0, t=50, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        font=dict(size=12),
    )
    return fig


def _signal_table(signal, ma_period):
    rows = [
        {"항목": "현재가",                 "값": f"{signal['current_price']:,.0f} 원"},
        {"항목": f"MA{ma_period} 이동평균", "값": f"{signal['ma_value']:,.0f} 원"},
        {"항목": "이평선 대비 차이",         "값": f"{signal['diff']:+,.0f} 원  ({signal['diff_pct']:+.2f}%)"},
        {"항목": "이평선 위치",             "값": "✅ 이평선 위" if signal['above_ma'] else "❌ 이평선 아래"},
        {"항목": "골든크로스",              "값": "🔥 발생" if signal['cross_up'] else "—"},
        {"항목": "데드크로스",              "값": "❄️ 발생" if signal['cross_down'] else "—"},
        {"항목": "전략 신호",               "값": signal['signal_label']},
    ]
    return pd.DataFrame(rows)


def render(broker, ticker, ma_period, interval_label="일봉 (1D)"):
    ticker_disp = get_ticker_display(ticker)
    asset_label = "주식" if is_stock(ticker) else "코인"
    add_log(f"--- 모니터링 렌더링: {ticker_disp} (Broker: {broker.name}) ---", "DEBUG")
    st.subheader(f"📡 실시간 MA 전략 모니터링 — {ticker_disp}")

    interval = INTERVAL_MAP.get(interval_label, "day")
    display_count = DISPLAY_COUNTS.get(interval, 90)

    # ── MA 선택 (멀티셀렉트) ────────────────────────────────────────────
    left_col, right_col = st.columns([4, 1])
    with left_col:
        selected_ma = st.multiselect(
            "📈 차트에 표시할 이동평균선",
            options=ALL_MA_OPTIONS, default=DEFAULT_MA,
            format_func=lambda x: f"MA{x}", key="chart_ma_select",
        )
    with right_col:
        auto_refresh = st.toggle("⏱ 자동갱신 (15s)", value=True, key="auto_refresh")

    all_periods = tuple(sorted(set(selected_ma + [int(ma_period)])))

    # ── 데이터 로드 (OHLCV 300s 캐시, 현재가 10s 캐시) ─────────────────
    try:
        # Chart: heavy OHLCV fetch - cached 300 s
        df = get_ohlcv_with_ma(broker, ticker, all_periods,
                               display_count=display_count, interval=interval)
        # Signal: MA cached 60s + price cached 10s
        signal = check_ma_signal(broker, ticker, int(ma_period), interval=interval)
    except Exception as e:
        add_log(f"[모니터링 오류] {e}", "ERROR")
        st.error(f"데이터 조회 중 오류 발생: {e}")
        return

    # ── 상단 지표 ──────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("현재가", f"{signal['current_price']:,.0f}원",
              f"{signal['diff']:+,.0f} (MA{ma_period} 대비)")
    c2.metric(f"MA{ma_period} [{interval_label}]", f"{signal['ma_value']:,.0f}원")
    c3.metric("이평선 위치", "✅ 이평선 위" if signal['above_ma'] else "❌ 이평선 아래")
    c4.metric("전략 신호", signal['signal_label'])

    st.divider()

    # ── 차트 + 테이블 ──────────────────────────────────────────────────
    chart_col, table_col = st.columns([3, 2])
    with chart_col:
        fig = _build_chart(df, selected_ma, int(ma_period), interval_label)
        st.plotly_chart(fig, use_container_width=True)
    with table_col:
        st.markdown(f"#### 📋 전략 계산 결과 (MA{ma_period} · {interval_label})")
        st.dataframe(_signal_table(signal, int(ma_period)),
                     use_container_width=True, hide_index=True)
        st.divider()
        st.markdown("#### 💰 잔고 현황 (전체)")
        try:
            balances = broker.get_balances()
            rows = []
            total_eval = 0.0
            
            for b in balances:
                curr = b['currency']
                amount = float(b['balance'])
                if curr == "KRW":
                    rows.append({"자산": "원화(KRW)", "보유량": f"{amount:,.0f}원", "평가금액": f"{amount:,.0f}원"})
                    total_eval += amount
                else:
                    # 현재가 조회를 시도 (현재 선택된 종목은 signal에서 가져오고, 나머지는 필요시 조회)
                    price = 0.0
                    if curr == ticker.replace("KRW-", ""):
                        price = signal['current_price']
                    else:
                        # 다른 종목의 현재가는 캐시된 가격이 있으면 좋겠지만, 일단 0으로 표시하거나 가볍게 한 번 조회
                        # 여기서는 간단히 하기 위해 선택된 종목 외에는 보유량 위주로 표시하고 총평가에는 현재 종목만 합산하거나, 
                        # 브로커에서 제공하는 평가금액 정보를 쓰면 좋지만 현재 API 구조상 보유량 위주로 구성
                        price = 0.0 
                    
                    name = get_ticker_display(curr)
                    unit = "주" if is_stock(curr) else "개"
                    eval_amt = amount * price
                    total_eval += eval_amt
                    
                    rows.append({
                        "자산": name,
                        "보유량": f"{amount:,.2f}" if not is_stock(curr) else f"{amount:,.0f}{unit}",
                        "평가금액": f"{eval_amt:,.0f}원" if price > 0 else "-"
                    })
            
            bal_df = pd.DataFrame(rows)
            st.dataframe(bal_df, use_container_width=True, hide_index=True)
            st.info(f"**총 추정 자산: {total_eval:,.0f}원**")
        except Exception as e:
            st.warning(f"잔고 조회 실패: {e}")

    st.divider()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.caption(
        f"마지막 업데이트: {now} | "
        f"차트 캐시: 5분 · MA캐시: 60s · 현재가: 10s | MA{ma_period} · {interval_label}"
    )

    # ── 자동 갱신 (JavaScript 타이머 - 다른 탭 렌더링 블록 없음) ─────────
    if auto_refresh:
        # st_autorefresh uses a JS interval, does NOT block Python rendering
        st_autorefresh(interval=15_000, key="monitor_refresh")
