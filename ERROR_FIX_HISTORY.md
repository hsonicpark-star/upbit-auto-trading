# ERROR_FIX_HISTORY — 오류 이력 및 수정 내역

> 이 문서는 발생한 오류와 해결책을 기록하여 **동일한 오류를 반복하지 않기 위한** 레퍼런스입니다.
> 새 오류 발생 시 아래 형식에 맞춰 추가한다.

---

## 📋 작성 형식

```
## [ERR-번호] 오류 제목
- **발생일**: YYYY-MM-DD
- **발생 환경**: 로컬 PC / VM / 공통
- **관련 파일**: 파일명
- **오류 메시지**: (실제 오류 텍스트)
- **원인**: 원인 설명
- **해결 방법**: 해결 방법 설명
- **재발 방지**: 앞으로 주의할 사항
```

---

## 오류 목록

| ID | 제목 | 환경 | 발생일 | 상태 |
|----|------|------|--------|------|
| [ERR-001](#err-001) | Upbit API IP 미인증 오류 | VM / 로컬 | 2026-03-20 | ✅ 해결 |
| [ERR-002](#err-002) | 모듈 누락 (pyupbit, streamlit-autorefresh 등) | VM | 2026-03-14 | ✅ 해결 |
| [ERR-003](#err-003) | Streamlit Fragment 렌더링 오류 | 로컬 / VM | 2026-03-21 | ✅ 해결 |
| [ERR-004](#err-004) | VM에서 Streamlit 포트 접속 불가 | VM | 2026-03-14 | ✅ 해결 |
| [ERR-005](#err-005) | `.env` 환경변수 로딩 실패 | 로컬 / VM | 2026-03-14 | ✅ 해결 |
| [ERR-006](#err-006) | 그리드 브로커 호환성 오류 (KIS broker로 그리드 실행) | 로컬 | 2026-03-21 | ✅ 해결 |

---

## 상세 내역

---

### ERR-001
## [ERR-001] Upbit API IP 미인증 오류

- **발생일**: 2026-03-20
- **발생 환경**: 로컬 PC (또는 VM 외 IP에서 API 호출 시)
- **관련 파일**: `broker_upbit.py`, `test_keys.py`
- **오류 메시지**:
  ```
  This is not a verified IP
  {'error': {'name': 'unauthorized_ip', 'message': 'This is not a verified IP.'}}
  ```
- **원인**:
  Upbit API 키 발급 시 등록한 허용 IP 목록에 현재 요청을 보내는 IP가 없음.
  로컬 PC에서 직접 API를 호출하거나, VM IP가 등록되지 않은 경우 발생.
- **해결 방법**:
  1. [Upbit 개발자 센터](https://upbit.com/mypage/open_api_management) → API 키 관리
  2. **허용할 IP 주소**에 **VM 외부 IP** (`34.22.87.189` 등) 만 등록
  3. 로컬 PC IP는 등록하지 않음 (로컬에서 직접 API 호출 금지)
- **재발 방지**:
  - ⚠️ 로컬 PC에서 `broker_upbit.py`를 직접 실행하거나 주문 함수를 `tabs/*.py`에서 직접 호출하지 않는다.
  - VM에서만 Upbit API를 호출한다. (CLAUDE.md 규칙 1 참조)

---

### ERR-002
## [ERR-002] 모듈 누락 (pyupbit, streamlit-autorefresh, websocket-client, plotly)

- **발생일**: 2026-03-14
- **발생 환경**: VM (Google Cloud)
- **관련 파일**: `requirements.txt`
- **오류 메시지**:
  ```
  ModuleNotFoundError: No module named 'pyupbit'
  ModuleNotFoundError: No module named 'streamlit_autorefresh'
  ModuleNotFoundError: No module named 'websocket'
  ModuleNotFoundError: No module named 'plotly'
  ```
- **원인**:
  VM에 Python 가상환경 설치 후 `pip install -r requirements.txt`가 누락되었거나,
  `requirements.txt`에 해당 패키지가 없었음.
- **해결 방법**:
  ```bash
  # VM SSH 접속 후
  cd ~/업비트\ 자동매매\ 공유
  source venv/bin/activate
  pip install pyupbit streamlit-autorefresh websocket-client plotly
  # requirements.txt 업데이트
  pip freeze > requirements.txt
  ```
- **재발 방지**:
  - 새 패키지 설치 시 반드시 `pip freeze > requirements.txt` 실행하여 동기화.
  - VM 재배포 전 `requirements.txt` 최신 상태 확인.

---

### ERR-003
## [ERR-003] Streamlit Fragment 렌더링 오류 (`@st.fragment` 관련)

- **발생일**: 2026-03-21
- **발생 환경**: 로컬 PC / VM 공통
- **관련 파일**: `app.py`, `tabs/tab_grid_backtest.py`
- **오류 메시지**:
  ```
  StreamlitAPIException: `st.xxx` commands are not allowed inside `@st.fragment`
  또는 백테스트 탭 클릭 시 내용이 표시되지 않음 (빈 화면)
  ```
- **원인**:
  - `@st.fragment` 데코레이터 내부에서 허용되지 않는 `st` 컴포넌트를 사용.
  - `@st.fragment` 함수를 `with tab:` 블록 안에서 호출하지 않고 외부에서 호출.
  - 브로커가 선택되지 않은 상태에서 탭 컨텐츠를 렌더링 시도.
- **해결 방법**:
  ```python
  # ✅ 올바른 패턴
  tab1, tab2 = st.tabs(["탭1", "탭2"])
  with tab1:
      render_tab1()  # fragment 함수 호출은 반드시 with tab 블록 내부에서

  # ❌ 잘못된 패턴
  tabs = st.tabs(["탭1", "탭2"])
  render_tab1()  # with 블록 밖에서 호출 → 렌더링 위치 오류
  ```
  - `@st.fragment` 내부에서는 `st.rerun()` 대신 fragment 재실행 메커니즘 활용.
  - 브로커 미선택 시 `st.warning("브로커를 선택하세요")` 후 `return` 처리.
- **재발 방지**:
  - 탭 렌더 함수는 항상 `with tab:` 블록 내에서 호출한다.
  - `@st.fragment` 함수 내에서 `st.rerun()` 호출 금지.

---

### ERR-004
## [ERR-004] VM에서 Streamlit 포트(8501) 외부 접속 불가

- **발생일**: 2026-03-14
- **발생 환경**: VM (Google Cloud)
- **관련 파일**: VM 방화벽 설정
- **오류 메시지**:
  브라우저에서 `http://[VM외부IP]:8501` 접속 시 연결 거부 또는 타임아웃
- **원인**:
  Google Cloud 방화벽 규칙에서 포트 8501이 열려 있지 않음.
  Streamlit 실행 시 `--server.address 0.0.0.0` 옵션 누락.
- **해결 방법**:
  ```powershell
  # 로컬 PowerShell에서 방화벽 규칙 추가
  gcloud compute firewall-rules create allow-streamlit `
    --allow tcp:8501 `
    --target-tags streamlit-server `
    --description "Streamlit port"

  gcloud compute instances add-tags [VM이름] --tags=streamlit-server --zone=[ZONE]
  ```
  ```bash
  # VM에서 실행 (반드시 0.0.0.0 바인딩)
  nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 > streamlit.log 2>&1 &
  ```
- **재발 방지**:
  - VM 재설치/재배포 후 방화벽 규칙 확인 필수.
  - `--server.address 0.0.0.0` 옵션은 `start.sh`에 항상 포함.

---

### ERR-005
## [ERR-005] `.env` 환경변수 로딩 실패 (API 키 인식 안 됨)

- **발생일**: 2026-03-14
- **발생 환경**: VM / 로컬 공통
- **관련 파일**: `.env`, `broker_upbit.py`, `broker_kis.py`
- **오류 메시지**:
  ```
  KeyError: 'UPBIT_ACCESS_KEY'
  또는 API 키가 None으로 인식됨
  ```
- **원인**:
  - `.env` 파일이 `gitignore`에 포함되어 VM으로 전송되지 않음.
  - `python-dotenv` 미설치 또는 `load_dotenv()` 호출 위치 문제.
  - `.env` 파일 경로가 실행 디렉토리와 다름.
- **해결 방법**:
  ```bash
  # VM에서 .env 파일 수동 생성
  nano ~/업비트\ 자동매매\ 공유/.env
  # 내용 입력:
  # UPBIT_ACCESS_KEY=your_key
  # UPBIT_SECRET_KEY=your_secret

  # python-dotenv 설치 확인
  pip install python-dotenv
  ```
  ```python
  # 코드 최상단에서 호출
  from dotenv import load_dotenv
  load_dotenv()  # 항상 가장 먼저 실행
  ```
- **재발 방지**:
  - `.env`는 `.gitignore`에 포함 → VM 배포 시 **수동으로 별도 생성** 필수.
  - `README` 또는 배포 체크리스트에 `.env` 수동 생성 단계 포함.
  - `load_dotenv()`는 `app.py` 또는 `main.py`의 import 직후 최상단에 배치.

---

### ERR-006
## [ERR-006] 그리드 매매 - 브로커 호환성 오류 (KIS 브로커로 그리드 실행)

- **발생일**: 2026-03-21
- **발생 환경**: 로컬 / VM 공통
- **관련 파일**: `tabs/tab_grid.py`, `strategy_grid.py`
- **오류 메시지**:
  ```
  AttributeError: 'BrokerKIS' object has no attribute 'place_order'
  또는 그리드 시작 시 오류로 즉시 중단
  ```
- **원인**:
  사이드바에서 KIS 브로커를 선택한 상태로 그리드매매 탭에서 시작 버튼을 누름.
  그리드 전략은 Upbit API 전용으로 구현되어 있어 KIS 브로커와 호환되지 않음.
- **해결 방법**:
  ```python
  # tab_grid.py 상단에 브로커 타입 검사 추가
  broker = st.session_state.get("broker")
  if not hasattr(broker, 'place_order') or broker.__class__.__name__ != 'BrokerUpbit':
      st.error("⚠️ 그리드 매매는 업비트 브로커에서만 사용 가능합니다.")
      return
  ```
- **재발 방지**:
  - 브로커 전용 기능 탭은 탭 진입 시 **브로커 타입 사전 검사** 필수.
  - 그리드 탭에 "업비트 전용" 안내 문구 상시 표시.

---

## 🆕 새 오류 추가 방법

1. 위 **오류 목록** 테이블에 새 행 추가 (ID는 ERR-NNN 순번)
2. **상세 내역** 섹션에 아래 템플릿으로 내용 작성:

```markdown
### ERR-NNN
## [ERR-NNN] 오류 제목

- **발생일**: YYYY-MM-DD
- **발생 환경**: 로컬 PC / VM / 공통
- **관련 파일**: 파일명
- **오류 메시지**:
  ```
  실제 오류 메시지
  ```
- **원인**: 원인 설명
- **해결 방법**: 해결 방법 (코드 예시 포함)
- **재발 방지**: 앞으로 주의할 사항
```

---

## 🕐 세션 작업 로그 (30분 단위 업데이트)

> AI 어시스턴트는 작업 세션 중 **30분마다** 또는 **세션 종료 시** 아래에 작업 내역을 추가한다.
> 형식: `### [날짜 시간] 세션 요약`

---

### [2026-03-22 16:05] CLAUDE.md 및 ERROR_FIX_HISTORY.md 초기 작성

- **작업 내용**:
  - `CLAUDE.md` 신규 생성 — VM/로컬 역할 분리 아키텍처 규칙 문서화
  - `ERROR_FIX_HISTORY.md` 신규 생성 — 과거 오류 6건 정리 (ERR-001 ~ ERR-006)
  - `CLAUDE.md`에 규칙 4 추가 — 30분마다 작업 내역 업데이트 규칙
- **수정 파일**:
  - `CLAUDE.md` (신규)
  - `ERROR_FIX_HISTORY.md` (신규)
- **발생 오류**: 없음
- **특이사항**: 과거 대화 로그(VM 배포, Grid Backtest, Upbit IP 오류)에서 오류 내역 수집하여 기록

