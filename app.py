"""
Upbit Auto Trading Bot - Streamlit Dashboard (Multi-Tab)
Tabs: Monitor | Log | Status | Connection | Order | Reserve | History

Each tab is wrapped in @st.fragment so widget interactions inside a tab
only re-run that fragment, NOT the entire app. This eliminates the full-page
reload on every button click / checkbox toggle.
"""
import os
import streamlit as st
import requests
import time
from dotenv import load_dotenv

from broker_upbit import BrokerUpbit
from broker_kis import BrokerKIS

from ws_manager import ob_manager as upbit_ws_manager
from kis_ws_manager import kis_ws_manager

from tabs import tab_monitor, tab_log, tab_status, tab_connection, tab_order, tab_reserve, tab_history
from utils import get_ticker_display

# ── 환경 변수 로드 ─────────────────────────────────────────────────────
load_dotenv()
upbit_access = os.getenv("UPBIT_ACCESS_KEY")
upbit_secret = os.getenv("UPBIT_SECRET_KEY")

kis_real_app_key = os.getenv("KIS_REAL_APP_KEY")
kis_real_app_secret = os.getenv("KIS_REAL_APP_SECRET")
kis_real_account = os.getenv("KIS_REAL_ACCOUNT")

kis_mock_app_key = os.getenv("KIS_MOCK_APP_KEY")
kis_mock_app_secret = os.getenv("KIS_MOCK_APP_SECRET")
kis_mock_account = os.getenv("KIS_MOCK_ACCOUNT")

# 브로커 객체 초기화
if "broker_upbit" not in st.session_state:
    st.session_state.broker_upbit = BrokerUpbit(upbit_access, upbit_secret)
if "broker_kis_real" not in st.session_state:
    st.session_state.broker_kis_real = BrokerKIS(kis_real_app_key, kis_real_app_secret, kis_real_account, mock=False)
if "broker_kis_mock" not in st.session_state:
    st.session_state.broker_kis_mock = BrokerKIS(kis_mock_app_key, kis_mock_app_secret, kis_mock_account, mock=True)

# ── 페이지 설정 ─────────────────────────────────────────────────────────
st.set_page_config(page_title="Auto-Bot Dashboard", layout="wide")
st.title("🚀 멀티 브로커 자동매매 대시보드")

# ── 사이드바 (전역 설정 - 사이드바 변경은 전체 rerun 허용) ─────────────
st.sidebar.header("🏢 거래소 (브로커) 설정")

# 브로커 선택
broker_choice = st.sidebar.radio(
    "거래소 선택",
    ["업비트 (Upbit)", f"한국투자증권 실전 ({kis_real_account})", f"한국투자증권 모의 ({kis_mock_account})"],
    index=0
)

if broker_choice.startswith("업"):
    st.session_state.broker = st.session_state.broker_upbit
    st.session_state.broker_key = "upbit"
    st.session_state.ob_manager = upbit_ws_manager
    TICKERS = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-ADA", "KRW-DOGE"]
    st.session_state.TICKERS = TICKERS
elif "실전" in broker_choice:
    st.session_state.broker = st.session_state.broker_kis_real
    st.session_state.broker_key = "kis_real"
    kis_ws_manager.set_credentials(kis_real_app_key, kis_real_app_secret, mock=False)
    st.session_state.ob_manager = kis_ws_manager
    TICKERS = ["005930", "000660", "035420", "068270"]
    st.session_state.TICKERS = TICKERS
else:
    st.session_state.broker = st.session_state.broker_kis_mock
    st.session_state.broker_key = "kis_mock"
    kis_ws_manager.set_credentials(kis_mock_app_key, kis_mock_app_secret, mock=True)
    st.session_state.ob_manager = kis_ws_manager
    TICKERS = ["005930", "000660", "035420", "068270"]
    st.session_state.TICKERS = TICKERS

st.sidebar.divider()
st.sidebar.header("🤖 봇 설정")
ticker = st.sidebar.selectbox("대상 마켓/종목", TICKERS, format_func=get_ticker_display)
ma_period = st.sidebar.number_input("이동평균선 기간 (기준선)", value=20, min_value=5, max_value=200)
interval_label = st.sidebar.radio(
    "캔들 단위",
    options=["일봉 (1D)", "4시간봉 (4H)"] if broker_choice.startswith("업") else ["일봉 (1D)"],  # KIS는 일봉만
    horizontal=True,
    key="sidebar_interval",
)

st.sidebar.divider()

# ── 연결 상태 확인 (KIS: 토큰 발급 시도, Upbit: 잔고 조회 시도) ──────────
def _check_connection(broker):
    try:
        if hasattr(broker, '_get_token'):
            # KIS의 경우 직접 토킹 발급 시도
            url = f"{broker.base_url}/oauth2/tokenP"
            body = {
                "grant_type": "client_credentials",
                "appkey": broker.app_key,
                "appsecret": broker.app_secret
            }
            res = requests.post(url, json=body, timeout=5)
            if res.status_code == 200:
                return True, "연결 성공"
            else:
                return False, f"KIS 에러: {res.text}"
        elif hasattr(broker, 'upbit'):
            balances = broker.upbit.get_balances()
            if isinstance(balances, list):
                return True, "연결 성공"
            else:
                return False, f"Upbit 에러: {balances}"
    except Exception as e:
        return False, f"예외 발생: {str(e)}"
    return False, "알 수 없는 상태"

_broker_key = st.session_state.get("broker_key", "upbit")
_conn_cache_key = f"api_connected_{_broker_key}"
_conn_msg_key = f"api_message_{_broker_key}"

if _conn_cache_key not in st.session_state:
    success, msg = _check_connection(st.session_state.broker)
    st.session_state[_conn_cache_key] = success
    st.session_state[_conn_msg_key] = msg

if "api_message_last_ts" not in st.session_state:
    st.session_state["api_message_last_ts"] = time.time()

if st.sidebar.button("🔄 연결 재시도"):
    success, msg = _check_connection(st.session_state.broker)
    st.session_state[_conn_cache_key] = success
    st.session_state[_conn_msg_key] = msg
    st.session_state["api_message_last_ts"] = time.time()
    st.rerun()

_acct = getattr(st.session_state.broker, 'account_number', '')
_acct_display = f" | 계좌: {_acct}" if _acct else ""
if st.session_state[_conn_cache_key]:
    st.sidebar.success(f"✅ {st.session_state.broker.name} 연결됨{_acct_display}")
else:
    st.sidebar.error(f"❌ {st.session_state.broker.name} 연결 실패{_acct_display}")
    with st.sidebar.expander("🔍 상세 에러 메시지", expanded=True):
        st.code(st.session_state.get(_conn_msg_key, "정보 없음"), language="json")

st.sidebar.divider()
with st.sidebar.expander("📋 최근 실행 로그 (trade.log)", expanded=False):
    try:
        if os.path.exists("trade.log"):
            with open("trade.log", "r", encoding="utf-8") as f:
                all_lines = f.readlines()
                # 린트 대응을 위해 명시적으로 슬라이싱
                start_idx = max(0, len(all_lines) - 15)
                recent_lines = all_lines[start_idx:]
                st.text("".join(recent_lines))
        else:
            st.info("로그 파일이 아직 생성되지 않았습니다.")
    except Exception as e:
        st.error(f"로그 읽기 실패: {e}")

# ── 탭 구성 ──────────────────────────────────────────────────────────────
t1, t2, t3, t4, t5, t6, t7 = st.tabs([
    "📡 모니터링",
    "📋 로그",
    "📌 작업현황",
    "🔌 연결상태",
    "🛒 수동주문",
    "📅 예약주문",
    "📂 거래내역",
])

# ── @st.fragment 래퍼 ─────────────────────────────────────────────────────
# Fragment 내부의 위젯 변경은 해당 fragment만 재실행 → 전체 앱 재로딩 없음

# 전역 설정에서 선택된 브로커를 탭으로 넘겨줍니다.
broker = st.session_state.broker

@st.fragment
def fragment_monitor():
    tab_monitor.render(broker, ticker, ma_period, interval_label)

@st.fragment
def fragment_log():
    tab_log.render()

@st.fragment
def fragment_status():
    tab_status.render()

@st.fragment
def fragment_connection():
    tab_connection.render(broker)

@st.fragment
def fragment_order():
    tab_order.render(broker, ticker)

@st.fragment
def fragment_reserve():
    tab_reserve.render(broker)

@st.fragment
def fragment_history():
    tab_history.render(broker)

# ── 탭별 fragment 호출 ────────────────────────────────────────────────────
with t1:
    fragment_monitor()
with t2:
    fragment_log()
with t3:
    fragment_status()
with t4:
    fragment_connection()
with t5:
    fragment_order()
with t6:
    fragment_reserve()
with t7:
    fragment_history()
