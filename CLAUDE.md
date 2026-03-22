# 업비트 자동매매 시스템 - 개발 규칙 및 아키텍처

## 시스템 아키텍처 원칙

### 역할 분리

| 구성요소 | 역할 | 허용 작업 |
|---------|------|-----------|
| **VM (Google Cloud)** | 실제 매매 엔진 | 주문 실행, 잔고 조회, 거래 내역 조회, 결과 기록 |
| **로컬 PC (Streamlit)** | UI / 대시보드 | 화면 표시, 매매 요청 전달, 결과 불러오기 |

---

## 핵심 규칙

### 규칙 1: 모든 매매·조회는 VM에서만 실행한다

- 주문 (매수 / 매도), 잔고 조회, 거래 내역 조회 등 **모든 API 호출은 VM에서만** 수행한다.
- 로컬 PC에서는 Upbit API에 직접 주문·조회 요청을 보내지 않는다.
- VM의 IP만 Upbit API 허용 IP로 등록한다.

```
# ✅ 허용 (VM에서 실행)
broker_upbit.py → place_order(), get_balance(), get_trades()

# ❌ 금지 (로컬 PC에서 직접 실행)
tabs/*.py, app.py → pyupbit.buy(), pyupbit.sell() 직접 호출
```

### 규칙 2: 로컬 Streamlit은 화면 표시 전용이다

- 로컬 PC의 Streamlit(`app.py`, `tabs/*.py`)은 **화면 렌더링과 사용자 입력 수집만** 담당한다.
- 직접 주문 API를 호출하는 코드를 `tabs/` 또는 `app.py`에 추가하지 않는다.
- 로컬에서는 VM이 기록한 결과 파일(JSON/CSV)을 읽어서 표시하는 것만 허용한다.

### 규칙 3: 매매 요청 흐름

```
[로컬 Streamlit UI]
    │  ① 사용자 요청 (매수/매도/설정 변경)
    ▼
[VM으로 전달]  ← SSH, REST API, 파일 공유, Google Cloud Storage 등
    │  ② VM이 요청 수신
    ▼
[VM 매매 엔진]
    │  ③ Upbit API 호출 → 주문 실행
    ▼
[VM 결과 저장]  ← changelog_upbit.json, 로그 파일 등
    │  ④ 결과 파일 업데이트
    ▼
[로컬 Streamlit UI]
    │  ⑤ 결과 파일 읽기 → 화면 표시
    ▼
[사용자 확인]
```

---

## 파일별 역할 정의

### VM 전용 파일 (로컬에서 직접 실행 금지)

| 파일 | 역할 |
|------|------|
| `broker_upbit.py` | Upbit 주문/조회 API 래퍼 |
| `broker_kis.py` | KIS 브로커 API 래퍼 |
| `strategy.py` | 매매 전략 로직 |
| `strategy_grid.py` | 그리드 전략 로직 |
| `main.py` | VM 자동매매 메인 루프 |
| `ws_manager.py` | 웹소켓 시세 수신 |
| `kis_ws_manager.py` | KIS 웹소켓 관리 |

### 로컬 PC 전용 파일 (주문 코드 추가 금지)

| 파일 | 역할 |
|------|------|
| `app.py` | Streamlit 앱 진입점 (화면 구성만) |
| `tabs/*.py` | 각 탭 UI 렌더링 |
| `utils.py` | UI 유틸리티 함수 |

### 공유 파일 (VM 기록 → 로컬 읽기)

| 파일 | 내용 |
|------|------|
| `changelog_upbit.json` | 업비트 거래 결과 로그 |
| `changelog_kis.json` | KIS 거래 결과 로그 |

---

## 개발 시 체크리스트

새 기능을 추가할 때 반드시 확인한다:

- [ ] 이 코드가 Upbit/KIS API를 직접 호출하는가?
  - **YES** → VM 파일(`broker_*.py`, `strategy*.py`, `main.py`)에만 작성한다.
- [ ] 이 코드가 `tabs/*.py` 또는 `app.py`에 있는가?
  - **YES** → API 직접 호출이 없는지 재확인한다. 있다면 제거하고 VM 전달 방식으로 변경한다.
- [ ] 결과를 화면에 표시하는가?
  - **YES** → VM이 기록한 JSON/CSV 파일을 읽어서 표시하는 방식으로 구현한다.

---

## 환경 변수 및 API 키

- `.env` 파일의 Upbit API Key는 **VM에서만** 사용된다.
- 로컬 PC의 `.env`에는 화면 표시에 필요한 최소한의 설정만 포함한다.
- Upbit API 허용 IP 목록에는 **VM의 외부 IP만** 등록한다 (로컬 PC IP 등록 금지).

---

## 참고: VM ↔ 로컬 통신 방식 (현재 구현)

- **결과 공유**: VM이 `changelog_upbit.json` 등에 결과를 기록하고, 로컬에서 Git Pull 또는 GCS 등으로 동기화하여 읽는다.
- **요청 전달**: 추후 구현 시 REST API 엔드포인트, SSH 커맨드, 또는 메시지 큐 방식을 사용한다.

---

## 작업 내역 업데이트 규칙

### 규칙 4: 30분마다 작업 내역을 기록한다

AI 어시스턴트(Claude/Antigravity)와 작업 세션 중, **30분에 한 번** 반드시 아래 항목을 업데이트한다.

#### 업데이트 대상 파일

| 파일 | 업데이트 내용 |
|------|-------------|
| `ERROR_FIX_HISTORY.md` | 새로 발생한 오류 및 해결 내역 추가 |
| `changelog_upbit.json` | 업비트 거래 실행 결과 (VM 자동 기록) |
| `CLAUDE.md` | 아키텍처 또는 규칙 변경 시에만 수정 |

#### 30분 업데이트 체크리스트

작업 중 30분이 경과하면 아래를 확인하고 기록한다:

- [ ] 이 세션에서 새로운 오류가 발생했는가?
  - **YES** → `ERROR_FIX_HISTORY.md`에 ERR-NNN 항목 추가
- [ ] 코드 파일이 수정되었는가?
  - **YES** → 수정된 파일명과 변경 요약을 메모 (Git commit message 형식)
- [ ] 새로운 규칙이나 아키텍처 변경이 있었는가?
  - **YES** → `CLAUDE.md` 해당 섹션 업데이트
- [ ] VM에서 실제 주문이 실행되었는가?
  - **YES** → `changelog_upbit.json` 동기화 확인

#### 작업 내역 기록 형식 (세션 로그)

각 30분 단위로 아래 형식으로 `ERROR_FIX_HISTORY.md` 하단 **세션 로그** 섹션에 추가한다:

```
### [YYYY-MM-DD HH:MM] 세션 요약
- 작업 내용: (무엇을 했는지)
- 수정 파일: (수정한 파일 목록)
- 발생 오류: (없으면 "없음")
- 특이사항: (없으면 "없음")
```

> **AI 어시스턴트에 대한 지시**: 작업 중 30분이 경과하거나 작업 세션이 종료될 때,
> 위 체크리스트를 확인하고 `ERROR_FIX_HISTORY.md`의 세션 로그를 자동으로 업데이트한다.
