"""
Tab: Status Dashboard
Project feature checklist with status tracking and revision history.
Changelog is stored per broker: changelog_upbit.json / changelog_kis.json
"""
import streamlit as st
import json
import os
from datetime import datetime
from tabs.tab_log import add_log

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))


def _changelog_path(broker_key=None) -> str:
    """Return broker-specific changelog path."""
    if broker_key is None:
        broker_key = st.session_state.get("broker_key", "upbit")
    return os.path.join(_BASE_DIR, f"changelog_{broker_key}.json")


def _load_changelog(broker_key=None):
    """Load changelog from broker-specific JSON file."""
    path = _changelog_path(broker_key)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_changelog(history: list, broker_key=None):
    """Persist the full revision history list to broker-specific JSON file."""
    path = _changelog_path(broker_key)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        add_log(f"[changelog 저장 오류] {e}", "ERROR")

# Default feature list with descriptions (브로커 공통)
DEFAULT_FEATURES = [
    {"id": "api_connect",     "name": "API 연결",           "desc": "거래소 API 키 인증 및 토큰 관리"},
    {"id": "balance_query",   "name": "잔고 조회",           "desc": "KRW 예수금 및 보유 자산 조회"},
    {"id": "price_query",     "name": "현재가 조회",          "desc": "실시간 종목 현재가 수신"},
    {"id": "ohlcv_query",     "name": "OHLCV 데이터 조회",   "desc": "일봉/캔들 데이터 수신 (업비트: 4시간봉 지원)"},
    {"id": "strategy_vb",     "name": "변동성 돌파 전략",     "desc": "[제거됨] 사용자 요청으로 전략에서 제외"},
    {"id": "strategy_ma",     "name": "이동평균선 전략",      "desc": "MA 계산, 골든/데드크로스 감지"},
    {"id": "buy_order",       "name": "시장가 매수",          "desc": "자동 매수 주문 실행"},
    {"id": "sell_order",      "name": "시장가 매도",          "desc": "자동 매도 주문 실행"},
    {"id": "manual_order",    "name": "수동 주문",            "desc": "수동 매수/매도 + 호가창 + 미체결 관리"},
    {"id": "reserve_order",   "name": "예약 주문",            "desc": "시간/조건 기반 예약 주문"},
    {"id": "log_system",      "name": "로그 시스템",          "desc": "활동 로그 기록 및 조회 (필터/검색)"},
    {"id": "dashboard",       "name": "실시간 대시보드",       "desc": "캔들차트 + MA + 전략 테이블 + 잔고"},
    {"id": "trade_history",   "name": "거래 내역 조회",       "desc": "체결/입금/출금 내역 조회"},
]

# Actual implementation status (reflects current codebase state)
INITIAL_STATUS = {
    "api_connect":   "✅ 정상",
    "balance_query": "✅ 정상",
    "price_query":   "✅ 정상",
    "ohlcv_query":   "✅ 정상",
    "strategy_vb":   "🏁 작업완료",   # Removed per user request
    "strategy_ma":   "✅ 정상",
    "buy_order":     "🔧 수정중",   # Commented out - awaiting live activation
    "sell_order":    "🔧 수정중",   # Commented out - awaiting live activation
    "manual_order":  "✅ 정상",
    "reserve_order": "✅ 정상",
    "log_system":    "✅ 정상",
    "dashboard":     "✅ 정상",
    "trade_history": "✅ 정상",
}

STATUS_OPTIONS = ["⏳ 대기", "✅ 정상", "❌ 오류", "🔧 수정중", "🏁 작업완료"]


INITIAL_REVISION_HISTORY = [
    {
        "time": "2026-03-07 14:02",
        "feature_id": "strategy_vb",
        "old": "⏳ 대기",
        "new": "🏁 작업완료",
        "note": "변동성 돌파 전략 제거 — 사용자 요청으로 strategy.py에서 get_target_price, check_buy_signal 함수 삭제",
    },
    {
        "time": "2026-03-07 14:02",
        "feature_id": "strategy_ma",
        "old": "⏳ 대기",
        "new": "✅ 정상",
        "note": "이동평균선 전략 전면 개편 — 골든/데드크로스 감지, check_ma_signal 추가",
    },
    {
        "time": "2026-03-07 14:02",
        "feature_id": "dashboard",
        "old": "⏳ 대기",
        "new": "✅ 정상",
        "note": "모니터링 탭 재작성 — Plotly 캔들차트 + MA 라인 + 전략 계산 테이블 + 잔고 현황",
    },
    {
        "time": "2026-03-07 14:07",
        "feature_id": "ohlcv_query",
        "old": "⏳ 대기",
        "new": "✅ 정상",
        "note": "MA 라인 끊김 수정 — display_count + max(MA period) 만큼 fetch 후 마지막 N개만 표시 (warm-up 처리)",
    },
    {
        "time": "2026-03-07 14:07",
        "feature_id": "ohlcv_query",
        "old": "✅ 정상",
        "new": "✅ 정상",
        "note": "4시간봉(minute240) 지원 추가 — INTERVAL_MAP 도입, 사이드바 라디오 버튼으로 봉 단위 선택",
    },
    {
        "time": "2026-03-07 14:11",
        "feature_id": "dashboard",
        "old": "✅ 정상",
        "new": "✅ 정상",
        "note": "사이드바 캔들 단위 이동 + 차트 MA 멀티셀렉트 추가 (MA5/10/20/60/120 중 선택 표시, 전략 MA는 ★굵은 점선)",
    },
    {
        "time": "2026-03-07 14:19",
        "feature_id": "manual_order",
        "old": "✅ 정상",
        "new": "✅ 정상",
        "note": "수동주문 탭 개편 — 지정가/시장가 실제 주문 활성화, 안전 체크박스 추가, 미체결 주문 현황 + 취소 버튼 추가",
    },
    {
        "time": "2026-03-07 14:19",
        "feature_id": "reserve_order",
        "old": "⏳ 대기",
        "new": "✅ 정상",
        "note": "거래내역 탭(tab_history.py) 신규 추가 — 체결 내역(done/cancel), 입금 내역, 출금 내역 3개 서브탭",
    },
    {
        "time": "2026-03-07 14:30",
        "feature_id": "dashboard",
        "old": "✅ 정상",
        "new": "✅ 정상",
        "note": "성능 최적화 — app.py 전역 time.sleep(10) 제거. 3단계 캐시 적용: OHLCV 300s / MA값 60s / 현재가 10s",
    },
    {
        "time": "2026-03-07 14:32",
        "feature_id": "strategy_ma",
        "old": "✅ 정상",
        "new": "✅ 정상",
        "note": "미완성 봉 제외 — get_ohlcv_with_ma: iloc[-(n+1):-1], get_ma_value: iloc[-2] 기준으로 완성된 봉만 MA 계산",
    },
]


def _get_broker_key():
    return st.session_state.get("broker_key", "upbit")


def _state_key(suffix: str) -> str:
    """브로커별 세션 키 생성: 예) 'upbit_feature_status', 'kis_revision_history'"""
    return f"{_get_broker_key()}_{suffix}"


def _init_state():
    sk = _state_key
    if sk("feature_status") not in st.session_state:
        st.session_state[sk("feature_status")] = dict(INITIAL_STATUS)
    if sk("status_checked_at") not in st.session_state:
        st.session_state[sk("status_checked_at")] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if sk("revision_history") not in st.session_state:
        loaded = _load_changelog()
        if loaded:
            st.session_state[sk("revision_history")] = loaded
        else:
            st.session_state[sk("revision_history")] = list(INITIAL_REVISION_HISTORY)
            _save_changelog(st.session_state[sk("revision_history")])
    if sk("feature_checked") not in st.session_state:
        st.session_state[sk("feature_checked")] = {f["id"]: False for f in DEFAULT_FEATURES}


def update_feature_status(feature_id: str, new_status: str, note: str = ""):
    """Update feature status, record in session_state AND persist to broker-specific changelog."""
    _init_state()
    sk = _state_key
    old_status = st.session_state[sk("feature_status")].get(feature_id, "⏳ 대기")
    st.session_state[sk("feature_status")][feature_id] = new_status
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record = {
        "time": ts,
        "feature_id": feature_id,
        "old": old_status,
        "new": new_status,
        "note": note,
    }
    st.session_state[sk("revision_history")].append(record)
    _save_changelog(st.session_state[sk("revision_history")])
    add_log(f"[상태변경] {feature_id}: {old_status} → {new_status} {note}", "INFO")


def render():
    _init_state()
    broker_key = _get_broker_key()
    _labels = {"upbit": "업비트 (Upbit)", "kis_real": "한국투자증권 (실전)", "kis_mock": "한국투자증권 (모의)"}
    broker_label = _labels.get(broker_key, broker_key)
    sk = _state_key

    st.subheader("📌 작업 현황 대시보드")
    st.caption(f"현재 거래소: **{broker_label}** — 수정 내역은 거래소별로 별도 관리됩니다.")

    subtab1, subtab2 = st.tabs(["📋 기능별 상태", f"🗂 수정 내역 ({broker_label})"])

    # ── Sub-tab 1: Feature checklist ──────────────────────────────────
    with subtab1:
        st.caption("각 기능의 현재 상태를 확인하고 직접 상태를 변경할 수 있습니다.")

        cols_header = st.columns([0.4, 2, 3, 2, 1.5])
        cols_header[0].markdown("**확인**")
        cols_header[1].markdown("**기능명**")
        cols_header[2].markdown("**설명**")
        cols_header[3].markdown("**현재 상태**")
        cols_header[4].markdown("**변경**")
        st.divider()

        for feat in DEFAULT_FEATURES:
            fid = feat["id"]
            current = st.session_state[sk("feature_status")][fid]

            c0, c1, c2, c3, c4 = st.columns([0.4, 2, 3, 2, 1.5])
            checked = c0.checkbox("확인", key=f"chk_{broker_key}_{fid}",
                                  value=st.session_state[sk("feature_checked")].get(fid, False),
                                  label_visibility="collapsed")
            st.session_state[sk("feature_checked")][fid] = checked
            c1.write(feat["name"])
            c2.write(feat["desc"])
            c3.write(current)
            new_status = c4.selectbox(
                "상태", STATUS_OPTIONS,
                index=STATUS_OPTIONS.index(current),
                key=f"sel_{broker_key}_{fid}",
                label_visibility="collapsed",
            )
            if new_status != current:
                update_feature_status(fid, new_status, "(사용자 수동 변경)")
                st.rerun()

        st.divider()
        if st.button("✅ 체크된 항목 → 작업완료로 변경", type="primary"):
            changed = False
            for feat in DEFAULT_FEATURES:
                fid = feat["id"]
                if st.session_state[sk("feature_checked")].get(fid):
                    if st.session_state[sk("feature_status")][fid] != "🏁 작업완료":
                        update_feature_status(fid, "🏁 작업완료", "(사용자 확인)")
                        changed = True
            if changed:
                st.success("선택된 항목이 작업완료로 변경되었습니다.")
                st.rerun()
            else:
                st.info("변경할 항목이 없습니다.")

    # ── Sub-tab 2: Revision history (브로커별) ─────────────────────────
    with subtab2:
        st.subheader(f"🗂 수정 내역 — {broker_label}")
        history = list(reversed(st.session_state[sk("revision_history")]))
        if not history:
            st.info("아직 수정 내역이 없습니다.")
        else:
            for rec in history:
                feat_name = next(
                    (f["name"] for f in DEFAULT_FEATURES if f["id"] == rec["feature_id"]),
                    rec["feature_id"]
                )
                st.markdown(
                    f"`{rec['time']}` **{feat_name}** : "
                    f"{rec['old']} → {rec['new']}"
                    + (f" _{rec['note']}_" if rec['note'] else "")
                )
