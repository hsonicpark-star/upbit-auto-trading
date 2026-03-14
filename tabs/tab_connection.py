"""
Tab: Connection Test
Verifies live communication with broker API.
"""
import time
import streamlit as st
from tabs.tab_log import add_log
from utils import get_ticker_display


def _test(label: str, fn):
    """Run fn(), measure latency, return (ok, latency_ms, result_or_error)."""
    t0 = time.time()
    try:
        result = fn()
        ms = int((time.time() - t0) * 1000)
        return True, ms, result
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        return False, ms, str(e)


def render(broker):
    broker_name = getattr(broker, "name", "브로커")
    st.subheader(f"🔌 {broker_name} 연결 상태 확인")
    st.caption("버튼을 눌러 각 API 엔드포인트의 응답 상태와 실제 데이터를 확인합니다.")

    active_tickers = st.session_state.get("TICKERS", ["KRW-BTC"])
    test_tickers = active_tickers[:3]
    ticker = st.selectbox("테스트 종목", test_tickers, key="conn_ticker",
                          format_func=get_ticker_display)

    if st.button("🔄 연결 테스트 실행", type="primary"):
        results = []

        # 1. Balance
        ok, ms, data = _test("잔고 조회", lambda: broker.get_balances())
        results.append(("💰 잔고 조회 (get_balances)", ok, ms, data if ok else None, data if not ok else None))
        add_log(f"잔고 조회 {'성공' if ok else '실패'} ({ms}ms)", "INFO" if ok else "ERROR")

        # 2. Current price
        ok, ms, data = _test("현재가 조회", lambda: broker.get_current_price(ticker))
        results.append(("📈 현재가 조회 (get_current_price)", ok, ms, data if ok else None, data if not ok else None))
        add_log(f"현재가 조회 {'성공' if ok else '실패'} ({ms}ms)", "INFO" if ok else "ERROR")

        # 3. OHLCV daily
        ok, ms, data = _test("일봉 데이터", lambda: broker.get_ohlcv(ticker, interval="day", count=3))
        results.append(("📊 일봉 OHLCV (get_ohlcv day)", ok, ms, data if ok else None, data if not ok else None))
        add_log(f"일봉 OHLCV {'성공' if ok else '실패'} ({ms}ms)", "INFO" if ok else "ERROR")

        st.divider()

        for label, ok, ms, success_data, err_msg in results:
            status_icon = "✅" if ok else "❌"
            col1, col2 = st.columns([3, 1])
            col1.markdown(f"{status_icon} **{label}**")
            col2.markdown(f"`{ms} ms`")

            if ok and success_data is not None:
                with st.expander("응답 데이터 보기"):
                    st.write(success_data)
            elif err_msg:
                st.error(f"오류: {err_msg}")

        all_ok = all(r[1] for r in results)
        st.divider()
        if all_ok:
            st.success("🎉 모든 API 연결이 정상입니다!")
        else:
            st.error("⚠️ 일부 API 연결에 문제가 있습니다. 로그 탭을 확인하세요.")
