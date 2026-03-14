"""
Tab: Log
All trading activity logs stored in session_state.
"""
import streamlit as st
from datetime import datetime
from streamlit_autorefresh import st_autorefresh


def add_log(message: str, level: str = "INFO"):
    """Add a log entry to session_state. Call from any tab."""
    if "logs" not in st.session_state:
        st.session_state.logs = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.logs.append({
        "time": timestamp,
        "level": level,
        "message": message,
    })


def render():
    # Auto-refresh every 3 s so new log entries from other fragments appear quickly
    st_autorefresh(interval=3_000, key="log_autorefresh")

    st.subheader("📋 작업 로그")

    if "logs" not in st.session_state or not st.session_state.logs:
        st.info("아직 기록된 로그가 없습니다.")
        return

    # Filter controls
    col1, col2 = st.columns([2, 1])
    with col1:
        keyword = st.text_input("🔍 로그 검색", placeholder="검색어 입력...")
    with col2:
        level_filter = st.selectbox(
            "레벨 필터",
            ["전체", "INFO", "WARNING", "ERROR", "ORDER"],
        )

    # Clear button
    if st.button("🗑 로그 초기화", type="secondary"):
        st.session_state.logs = []
        st.rerun()

    st.divider()

    # Display logs (newest first)
    logs = list(reversed(st.session_state.logs))

    if level_filter != "전체":
        logs = [l for l in logs if l["level"] == level_filter]
    if keyword:
        logs = [l for l in logs if keyword.lower() in l["message"].lower()]

    if not logs:
        st.warning("조건에 맞는 로그가 없습니다.")
        return

    level_colors = {
        "INFO":    "🔵",
        "WARNING": "🟡",
        "ERROR":   "🔴",
        "ORDER":   "🟢",
    }

    for entry in logs:
        icon = level_colors.get(entry["level"], "⚪")
        st.markdown(
            f"`{entry['time']}` {icon} **[{entry['level']}]** {entry['message']}"
        )
