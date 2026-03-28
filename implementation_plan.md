# VM 중심 자동매매 시스템 - 구현 계획

## 목표

현재 구조(로컬 PC에서 전략 계산 → VM 주문)를 아래 구조로 전환한다.

```
[GitHub Actions 스케줄 / Streamlit 수동 실행]
           ↓ (VM에서 실행)
   ┌────────────────────────┐
   ↓                        ↓
run_auto_trade()     run_manual_order()
   ↓                        ↓
[시세·캔들·잔고 조회]  [즉시 주문 실행]
   ↓
[Donchian(4H) + SMA(1D) 계산]
   ↓
[signal_state.json 비교 → 전환 시 주문]
   ↓
[balance_cache.json / signal_state.json / trade_log.json 저장]
   ↓
[GitHub 동기화 (Actions: 자동 커밋)]
   ↓
[Streamlit(로컬)이 GitHub Raw URL에서 JSON 읽기]
   ↓
[대시보드 / 거래 내역 / 운영 로그 표시]
```

**핵심 원칙**: 로컬 PC 꺼져도 VM이 독립 작동. 로컬 Streamlit은 읽기 전용.

---

## User Review Required

> [!IMPORTANT]
> **dry-run 기간**: 처음에는 실제 주문을 실행하지 않고 `DRY_RUN=true` 환경변수로 테스트합니다. 실제 거래 허용 시점은 사용자가 직접 확인 후 결정합니다.

> [!IMPORTANT]
> **GitHub 리포지토리 접근**: JSON 결과 파일을 GitHub(`signal_state.json`, `trade_log.json`, `balance_cache.json`)에 커밋하여 Streamlit에서 읽습니다. **리포지토리가 Public이면 API 키가 노출되지 않도록** [.gitignore](file:///d:/05.%EC%9E%90%EB%8F%99%ED%99%94%EA%B5%90%EC%9C%A1/12.API/%EC%97%85%EB%B9%84%ED%8A%B8%20%EC%9E%90%EB%8F%99%EB%A7%A4%EB%A7%A4%20%EA%B3%B5%EC%9C%A0/.gitignore) / [.env](file:///d:/05.%EC%9E%90%EB%8F%99%ED%99%94%EA%B5%90%EC%9C%A1/12.API/%EC%97%85%EB%B9%84%ED%8A%B8%20%EC%9E%90%EB%8F%99%EB%A7%A4%EB%A7%A4%20%EA%B3%B5%EC%9C%A0/.env) 관리가 필요합니다.

> [!WARNING]
> **Donchian 채널 구현**: 다이어그램에 `Donchian(115/105, 4H) + SMA(29, 1D)` 파라미터가 보입니다. 이 수치가 맞는지 확인이 필요합니다. (115/105 = 상단/하단 기간, 29 = SMA 기간)

---

## Proposed Changes

### 1. VM 트레이딩 엔진

#### [NEW] [vm_trader.py](file:///d:/05.자동화교육/12.API/업비트 자동매매 공유/vm_trader.py)

VM에서 단독 실행되는 트레이딩 엔진.

```python
# 실행 방법
python vm_trader.py --mode auto    # 자동매매 (GitHub Actions 호출)
python vm_trader.py --mode manual --side buy --ticker KRW-BTC --amount 10000
```

주요 기능:
- `run_auto_trade()`: 시세·캔들 조회 → Donchian + SMA 신호 계산 → 이전 상태와 비교 → 전환 시 주문
- `run_manual_order()`: CLI 인자로 즉시 시장가 주문
- `DRY_RUN=true` 환경변수 시 주문 함수 호출 건너뜀 (모의 로그만)
- 결과를 `data/balance_cache.json`, `data/signal_state.json`, `data/trade_log.json`에 저장

#### [NEW] data/ 디렉토리 (JSON 파일들)

```
data/
  balance_cache.json   # 잔고 스냅샷 (broker.get_balances() 결과)
  signal_state.json    # 현재 전략 신호 상태 (ticker, signal, price, ts)
  trade_log.json       # 주문 기록 + 오류 기록 목록
```

---

### 2. GitHub Actions 스케줄러

#### [NEW] [.github/workflows/auto_trade.yml](file:///d:/05.자동화교육/12.API/업비트 자동매매 공유/.github/workflows/auto_trade.yml)

```yaml
on:
  schedule:
    - cron: '0 */4 * * *'   # 4시간마다
  workflow_dispatch:          # 수동 트리거 가능
```

Steps:
1. repo checkout
2. Python 환경 + `pip install -r requirements.txt`
3. `python vm_trader.py --mode auto`
4. `data/*.json` 변경분 git commit & push

> [!NOTE]
> GitHub Actions Secrets에 `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY` 등록 필요.

---

### 3. 로컬 Streamlit 탭 (읽기 전용)

#### [NEW] [tabs/tab_vm_status.py](file:///d:/05.자동화교육/12.API/업비트 자동매매 공유/tabs/tab_vm_status.py)

GitHub Raw URL에서 JSON을 주기적으로 읽어 표시.

표시 항목:
- 현재 잔고 (KRW / BTC 등)
- 현재 신호 상태 (매수/매도/홀드) + 마지막 업데이트 시각
- 최근 거래 로그 (주문 성공/실패 내역)
- 오류 목록

#### [MODIFY] [app.py](file:///d:/05.자동화교육/12.API/업비트 자동매매 공유/app.py)

- `tab_vm_status` 임포트 추가
- `"🖥️ VM 현황"` 탭 추가 (t11)

---

## Verification Plan

### 1. Dry Run 자동 매매 테스트 (VM 또는 로컬)

```bash
# 로컬에서 dry-run 테스트
DRY_RUN=true python vm_trader.py --mode auto
```

확인 사항:
- `data/signal_state.json` 생성·내용 확인
- `data/balance_cache.json` 생성·내용 확인
- `data/trade_log.json` 에 실행 로그 기록 확인
- 콘솔에 "DRY RUN" 표시 확인 (실제 주문 없음)

### 2. GitHub Actions 수동 트리거

GitHub → Actions → `Auto Trade` → `Run workflow` 버튼으로 수동 실행.  
실행 후 `data/*.json` 커밋이 생성되는지 확인.

### 3. Streamlit 탭 확인

```bash
streamlit run app.py
```

"🖥️ VM 현황" 탭을 열어 JSON 데이터가 정상 표시되는지 확인.
