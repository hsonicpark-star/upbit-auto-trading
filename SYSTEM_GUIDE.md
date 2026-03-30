# 멀티 브로커 자동매매 시스템 구축 가이드

> 업비트(암호화폐) + 한국투자증권(주식) 자동매매를 처음부터 VM 배포까지 구축한 전 과정을 정리한 문서입니다.

---

## 목차

1. [시스템 전체 개요](#1-시스템-전체-개요)
2. [개발 여정 (로컬 → VM)](#2-개발-여정-로컬--vm)
3. [아키텍처 구조](#3-아키텍처-구조)
4. [구성 요소 상세 설명](#4-구성-요소-상세-설명)
5. [데이터 흐름](#5-데이터-흐름)
6. [전략 설명](#6-전략-설명)
7. [파일 구조](#7-파일-구조)
8. [환경 설정 가이드](#8-환경-설정-가이드)
9. [운영 체크리스트](#9-운영-체크리스트)
10. [자주 발생하는 문제와 해결법](#10-자주-발생하는-문제와-해결법)

---

## 1. 시스템 전체 개요

### 무엇을 만들었나?

```
┌─────────────────────────────────────────────────────┐
│           멀티 브로커 자동매매 시스템                      │
│                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐  │
│  │  업비트   │    │  한국투자  │    │  LAA 전략    │  │
│  │ (암호화폐) │    │ 증권(주식) │    │  (해외 ETF)  │  │
│  └──────────┘    └──────────┘    └──────────────┘  │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │        Streamlit 대시보드 (UI)               │   │
│  │  모니터링 / 수동주문 / 예약주문 / 백테스트 등    │   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### 핵심 원칙

> **모든 실제 거래는 VM에서만 실행한다.**
> 로컬 PC는 화면 표시와 명령 전달만 담당한다.

이 원칙이 중요한 이유:
- 업비트 API는 **허용 IP를 등록**해야 하는데, VM의 고정 IP만 등록하면 보안이 강화됨
- 로컬 PC는 꺼져도 VM은 24시간 계속 자동매매 가능
- 여러 장소에서 대시보드 접속 가능 (VM IP로 접속)

---

## 2. 개발 여정 (로컬 → VM)

### 1단계: 로컬에서 시작

처음에는 모든 코드를 **로컬 PC**에서 개발했습니다.

```
[로컬 PC]
  ├── app.py (Streamlit 대시보드)
  ├── broker_upbit.py (업비트 API 연동)
  ├── broker_kis.py (한국투자증권 API 연동)
  └── strategy.py (매매 전략)
```

**문제점 발견:**
- 로컬 PC를 끄면 자동매매 중단
- 업비트 API가 로컬 PC IP를 허용 IP로 등록해야 하는데, 매번 IP가 바뀜
- PC가 꺼져있으면 예약주문도 실행 안 됨

### 2단계: VM 도입 결정

**Google Cloud VM** (e2-micro, 무료 티어)을 도입했습니다.

```
[로컬 PC]          [Google Cloud VM]
  대시보드 UI   →     실제 매매 실행
  화면 표시     ←     결과 파일 저장
```

**VM 사양:**
- 인스턴스: `e2-micro` (무료 티어)
- 리전: `us-central1-a`
- OS: Debian Linux
- 외부 IP: `35.209.252.75` (고정)

### 3단계: GitHub 연동

VM과 로컬 PC의 코드를 GitHub으로 동기화했습니다.

```
[로컬 PC에서 코드 수정]
        ↓ git push
[GitHub 리포지토리]
        ↓ git pull
[VM에서 최신 코드 실행]
```

### 4단계: 안정성 강화 (7단계 계획)

| 단계 | 내용 | 설명 |
|------|------|------|
| 1 | Dry Run 검증 | 실제 주문 없이 로직만 테스트 |
| 2 | 기록 체계 | trade_log.csv, 수익률 자동 계산 |
| 3 | VM 전략 엔진 | Donchian+SMA 전략 자동 실행 |
| 4 | 안정성 강화 | flock(중복방지), retry(재시도), backup(백업) |
| 5 | 예약주문 VM 이관 | 세션 저장 → 파일 저장, cron 실행 |
| 6 | 동기화 표시 개선 | 데이터 신선도, cron 헬스체크 표시 |
| 7 | GitHub Actions 백업 | VM 다운 감지 + Telegram 알림 |

---

## 3. 아키텍처 구조

### 전체 구조도

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Repository                         │
│                  (코드 + data/*.json 백업)                    │
└──────────────────────┬──────────────────┬───────────────────┘
                       │ git pull          │ git push (자동)
                       ▼                  │
┌──────────────────────────────────────┐  │
│         Google Cloud VM              │  │
│         (35.209.252.75)              │──┘
│                                      │
│  ┌─────────────────────────────────┐ │
│  │  cron (4시간마다)                │ │
│  │  vm_trader.py --mode auto       │ │
│  │  ├── Donchian+SMA 신호 계산      │ │
│  │  ├── 신호 전환 시 주문 실행       │ │
│  │  ├── data/*.json 저장           │ │
│  │  └── GitHub에 자동 push         │ │
│  └─────────────────────────────────┘ │
│                                      │
│  ┌─────────────────────────────────┐ │
│  │  cron (1분마다)                  │ │
│  │  vm_trader.py --mode reserve    │ │
│  │  └── 예약주문 체크 & 실행         │ │
│  └─────────────────────────────────┘ │
│                                      │
│  ┌─────────────────────────────────┐ │
│  │  Streamlit (포트 8501)           │ │
│  │  systemd 서비스로 24시간 실행     │ │
│  └─────────────────────────────────┘ │
│                                      │
│  ┌─────────────────────────────────┐ │
│  │  data/ 폴더                     │ │
│  │  ├── signal_state.json          │ │
│  │  ├── balance_cache.json         │ │
│  │  ├── trade_log.json             │ │
│  │  ├── trade_log.csv              │ │
│  │  ├── reserve_orders.json        │ │
│  │  └── backup/ (7일치 보관)        │ │
│  └─────────────────────────────────┘ │
└──────────────────────────────────────┘
         ▲                    │
         │ 브라우저 접속        │ Telegram 알림
         │ 35.209.252.75:8501  ▼
┌──────────────┐      ┌──────────────┐
│  로컬 PC     │      │  스마트폰     │
│  (대시보드   │      │  (Telegram)  │
│   열람만)    │      └──────────────┘
└──────────────┘

┌──────────────────────────────────────┐
│      GitHub Actions (30분마다)        │
│  vm_monitor.yml                      │
│  ├── signal_state.json 신선도 체크    │
│  └── 5시간 이상 미업데이트 → Telegram │
└──────────────────────────────────────┘
```

### 역할 분리 요약

| 구성요소 | 역할 | 실행 위치 |
|---------|------|---------|
| `vm_trader.py` | 자동매매 엔진 | VM cron |
| `app.py` + `tabs/` | 대시보드 UI | VM (Streamlit) |
| `broker_upbit.py` | 업비트 API 래퍼 | VM |
| `broker_kis.py` | 한투 API 래퍼 | VM |
| `strategy_laa.py` | LAA 전략 계산 | VM / 로컬 |
| `data/*.json` | 상태 공유 파일 | VM 저장 → GitHub 백업 |

---

## 4. 구성 요소 상세 설명

### 4.1 vm_trader.py — 핵심 엔진

VM에서 실행되는 자동매매의 핵심 파일입니다.

**실행 모드:**
```bash
# 자동매매 (cron 4시간마다)
python vm_trader.py --mode auto

# 예약주문 체크 (cron 1분마다)
python vm_trader.py --mode reserve

# 수동 매수 (금액 지정)
python vm_trader.py --mode manual --side buy --ticker KRW-BTC --amount 50000

# 수동 매도 (수량 지정)
python vm_trader.py --mode manual --side sell --ticker KRW-BTC --amount 0.001
```

**안정성 기능:**
- **flock**: 같은 프로세스가 중복 실행되는 것을 방지 (cron 겹침 방지)
- **retry**: API 오류 시 5초 간격으로 최대 3회 자동 재시도
- **backup**: 실행 전 data/ 파일을 backup/ 폴더에 타임스탬프로 백업 (7일 보관)
- **crash 알림**: 예외 발생 시 Telegram으로 즉시 알림

### 4.2 Streamlit 대시보드 — UI

브라우저로 접속하는 대시보드입니다. `35.209.252.75:8501`

**탭 구성:**

| 탭 | 기능 |
|----|------|
| 모니터링 | 실시간 시세, 잔고 현황 |
| 로그 | 실행 로그 확인 |
| 작업현황 | 진행 중인 작업 추적 |
| 연결상태 | 업비트/한투 API 연결 확인 |
| 수동주문 | 즉시 매수/매도 실행 |
| 예약주문 | 시간/조건 기반 주문 예약 |
| 거래내역 | 체결 내역 조회 |
| 그리드매매 | 그리드 전략 설정/실행 |
| 백테스트 | 전략 과거 성과 시뮬레이션 |
| LAA 전략 | 해외 ETF 자산배분 전략 |
| VM 현황 | VM 상태, cron 헬스, 수익률 |

### 4.3 data/ 폴더 — 상태 공유

VM의 자동매매 결과를 저장하는 JSON/CSV 파일들입니다.

```
data/
├── signal_state.json      # 현재 전략 신호 (BUY/SELL/HOLD)
│                          # 현재가, SMA, Donchian 값 포함
│                          # 수익률, 평균매수가, 보유량 포함
│
├── balance_cache.json     # 잔고 현황
│                          # KRW, BTC 등 보유 자산 목록
│
├── trade_log.json         # 거래 이력 (최신 500건)
│                          # RUN: 실행 기록
│                          # ORDER: 주문 기록
│                          # MANUAL: 수동 주문
│                          # RESERVE: 예약 주문
│                          # ERROR: 오류 기록
│
├── trade_log.csv          # 거래 이력 CSV (엑셀 분석용)
│
├── reserve_orders.json    # 예약주문 목록
│                          # 상태: 대기중/완료/취소/실패
│
└── backup/                # 자동 백업 (7일치)
    ├── signal_state_20260328_155039.json
    └── balance_cache_20260328_155039.json
```

### 4.4 crontab — 스케줄러

VM에서 자동으로 실행되는 스케줄입니다.

```bash
# 4시간마다 자동매매 실행
0 */4 * * * cd /home/hsonic_park/upbit-bot && \
  /home/hsonic_park/upbit-venv/bin/python vm_trader.py --mode auto \
  >> /home/hsonic_park/upbit-bot/trade.log 2>&1

# 1분마다 예약주문 체크
* * * * * cd /home/hsonic_park/upbit-bot && \
  /home/hsonic_park/upbit-venv/bin/python vm_trader.py --mode reserve \
  >> /home/hsonic_park/upbit-bot/reserve.log 2>&1
```

### 4.5 GitHub Actions — 백업 모니터링

GitHub에서 30분마다 자동 실행되는 워크플로우입니다.

**vm_monitor.yml:**
- signal_state.json의 `updated_at` 확인
- 5시간 이상 미업데이트 → VM 다운으로 판단
- Telegram으로 알림 전송
- GitHub Actions 탭에서 빨간 X로 표시

**auto_trade.yml:**
- 스케줄 비활성화 (VM cron이 주력)
- 수동 실행(workflow_dispatch)만 허용
- 테스트/긴급 실행용

### 4.6 Telegram 알림

자동매매 관련 중요 이벤트를 스마트폰으로 알려줍니다.

| 알림 | 발생 시점 |
|------|---------|
| 🟢 매수 신호 전환 | SELL/HOLD → BUY 전환 시 |
| 🔴 매도 신호 전환 | BUY/HOLD → SELL 전환 시 |
| ✅ 주문 완료 | 매수/매도 주문 성공 시 |
| ❌ 주문 실패 | 주문 오류 발생 시 |
| ⚠️ VM 오류 | 지표 계산 실패 시 |
| 🚨 VM 크래시 | 예상치 못한 예외 발생 시 |
| 🚨 VM 다운 감지 | GitHub Actions가 5시간 미업데이트 감지 시 |

---

## 5. 데이터 흐름

### 자동매매 실행 흐름

```
[cron 4시간마다 실행]
        ↓
[vm_trader.py --mode auto]
        ↓
1. SingleInstanceLock 획득 (중복 실행 방지)
        ↓
2. backup_state() — 현재 상태 파일 백업
        ↓
3. save_balance() — 잔고 조회 → balance_cache.json 저장
        ↓
4. get_signal() — 현재가 + Donchian + SMA 계산
   ├── calc_donchian(): 4H 캔들 115개로 상단/하단 계산
   └── calc_sma(): 1D 캔들 29개로 이동평균 계산
        ↓
5. 신호 판단
   ├── 현재가 > Donchian상단 AND SMA29 위 → BUY
   ├── 현재가 < Donchian하단 OR SMA29 아래 → SELL
   └── 그 외 → HOLD
        ↓
6. 이전 신호와 비교
   ├── BUY 전환 → execute_buy() — KRW 99.95% 시장가 매수
   ├── SELL 전환 → execute_sell() — BTC 전량 시장가 매도
   └── 신호 유지 → 주문 없음
        ↓
7. 수익률 계산 — 평균매수가 vs 현재가
        ↓
8. signal_state.json 저장 (신호 + 지표 + 수익률)
        ↓
9. trade_log.json / trade_log.csv 기록
        ↓
10. Telegram 알림 (신호 전환 시)
        ↓
11. git_push_data() — GitHub에 data/ 자동 커밋
        ↓
[Lock 해제]
```

### 예약주문 흐름

```
[사용자가 Streamlit에서 예약 등록]
        ↓
[data/reserve_orders.json에 저장]
        ↓
[cron 1분마다]
[vm_trader.py --mode reserve]
        ↓
[reserve_orders.json 읽기]
        ↓
각 주문 체크:
├── 시간 지정: 현재시간 >= 실행시각 → 실행
├── 목표가 돌파: 현재가 >= 목표가 → 실행
├── 이평선 돌파: 현재가 > MA → 실행
└── 리밸런싱: 현재시간 >= 실행시각 → 실행
        ↓
[주문 실행 → 상태 업데이트 → Telegram 알림]
```

---

## 6. 전략 설명

### 6.1 Donchian + SMA 전략 (업비트 BTC)

**개념:**
- **Donchian 채널**: 일정 기간의 최고가/최저가로 추세 방향 파악
- **SMA (단순이동평균)**: 현재가가 평균 위에 있으면 상승 추세

**매수 조건 (BUY):**
```
현재가 > Donchian 상단 (115개 4H 캔들의 최고가)
AND
현재가 > SMA29 (29일 종가 평균)
```

**매도 조건 (SELL):**
```
현재가 < Donchian 하단 (105개 4H 캔들의 최저가)
OR
현재가 < SMA29
```

**신호 전환 시에만 주문 실행:**
- SELL → BUY 전환 시만 매수 (중복 매수 방지)
- BUY → SELL 전환 시만 매도 (중복 매도 방지)

**파라미터:**
```python
DONCHIAN_HIGH = 115   # 4H 상단 기간 (약 19일)
DONCHIAN_LOW  = 105   # 4H 하단 기간 (약 17일)
SMA_PERIOD    = 29    # 1D SMA 기간
```

### 6.2 LAA 전략 (한국투자증권 해외 ETF)

**LAA = Lethargic Asset Allocation (게으른 자산배분)**

**대상 자산:**
| 심볼 | 이름 | 역할 |
|------|------|------|
| SPY | S&P 500 ETF | 주요 자산 |
| IWM | Russell 2000 ETF | 주요 자산 |
| GLD | 금 ETF | 주요 자산 |
| BIL | 단기국채 ETF | 방어 자산 |

**전략 로직:**
```
캐너리 신호: SPY > 200일 이동평균?
    ├── YES (강세장): SPY/IWM/GLD 중 12개월 수익률 1위 75% + BIL 25%
    └── NO (약세장): BIL 100%
```

**리밸런싱 주기:** 월 1회 / 분기 / 반기 / 년 선택 가능

---

## 7. 파일 구조

```
업비트 자동매매 공유/
│
├── app.py                    # Streamlit 앱 진입점 (탭 구성)
├── vm_trader.py              # VM 자동매매 엔진 (핵심)
├── broker_upbit.py           # 업비트 API 래퍼
├── broker_kis.py             # 한국투자증권 API 래퍼
├── strategy.py               # 기본 매매 전략
├── strategy_grid.py          # 그리드 매매 전략
├── strategy_laa.py           # LAA 자산배분 전략
├── utils.py                  # UI 유틸리티 함수
├── requirements.txt          # Python 패키지 목록
├── .env                      # API 키 (Git에 올리지 않음!)
│
├── tabs/                     # Streamlit 탭별 UI
│   ├── tab_monitor.py        # 모니터링
│   ├── tab_log.py            # 로그
│   ├── tab_status.py         # 작업현황
│   ├── tab_connection.py     # 연결상태
│   ├── tab_order.py          # 수동주문
│   ├── tab_reserve.py        # 예약주문 (파일 기반)
│   ├── tab_history.py        # 거래내역
│   ├── tab_grid.py           # 그리드매매
│   ├── tab_grid_backtest.py  # 그리드 백테스트
│   ├── tab_laa.py            # LAA 전략
│   └── tab_vm_status.py      # VM 현황
│
├── data/                     # VM 상태 파일 (자동 생성)
│   ├── signal_state.json
│   ├── balance_cache.json
│   ├── trade_log.json
│   ├── trade_log.csv
│   ├── reserve_orders.json
│   └── backup/
│
├── .github/
│   └── workflows/
│       ├── auto_trade.yml    # 수동 실행용 (스케줄 비활성화)
│       └── vm_monitor.yml    # VM 다운 감지 (30분마다)
│
├── CLAUDE.md                 # 개발 규칙 (AI 어시스턴트용)
├── SYSTEM_GUIDE.md           # 이 문서
└── walkthrough.md            # 구현 완료 보고
```

---

## 8. 환경 설정 가이드

### 8.1 .env 파일 구성

```env
# 업비트 API
UPBIT_ACCESS_KEY=your_access_key
UPBIT_SECRET_KEY=your_secret_key

# 한국투자증권 API
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_ACCOUNT_NO=12345678-01

# Telegram 알림
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxyz
TELEGRAM_CHAT_ID=1234567890

# 운영 모드
DRY_RUN=false   # true: 테스트 모드 (실제 주문 안 함)
```

### 8.2 업비트 API 설정

1. [업비트 개발자센터](https://upbit.com/mypage/open_api_management) 접속
2. Open API 관리 → 키 발급
3. **허용 IP 등록**: VM 외부 IP (`35.209.252.75`)만 등록
   - 로컬 PC IP는 등록하지 않음 (보안)
4. 권한: 자산조회, 주문조회, 주문하기

### 8.3 Telegram 봇 설정

1. 텔레그램에서 `@BotFather` 검색
2. `/newbot` 명령 → 봇 이름 입력 → **토큰** 발급
3. 봇과 대화 시작
4. `@userinfobot`에서 **Chat ID** 확인
5. .env에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 등록

### 8.4 GitHub Secrets 설정

GitHub 리포 → Settings → Secrets and variables → Actions

| Secret 이름 | 값 |
|------------|-----|
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 |
| `TELEGRAM_CHAT_ID` | 텔레그램 채팅 ID |
| `UPBIT_ACCESS_KEY` | 업비트 액세스 키 (선택) |
| `UPBIT_SECRET_KEY` | 업비트 시크릿 키 (선택) |

### 8.5 VM crontab 설정

```bash
crontab -e
```

아래 내용 추가:
```
# 자동매매 (4시간마다)
0 */4 * * * cd /home/hsonic_park/upbit-bot && /home/hsonic_park/upbit-venv/bin/python vm_trader.py --mode auto >> /home/hsonic_park/upbit-bot/trade.log 2>&1

# 예약주문 체크 (1분마다)
* * * * * cd /home/hsonic_park/upbit-bot && /home/hsonic_park/upbit-venv/bin/python vm_trader.py --mode reserve >> /home/hsonic_park/upbit-bot/reserve.log 2>&1
```

### 8.6 Streamlit 서비스 (systemd)

```bash
# 서비스 상태 확인
sudo systemctl status upbit-dashboard

# 서비스 시작/재시작/중지
sudo systemctl start upbit-dashboard
sudo systemctl restart upbit-dashboard
sudo systemctl stop upbit-dashboard

# 부팅 시 자동 시작 설정
sudo systemctl enable upbit-dashboard
```

---

## 9. 운영 체크리스트

### 매일 확인

- [ ] VM 현황 탭 → 전략 데이터 "✅ 정상" 확인
- [ ] cron(1분) 상태 "✅ 정상" 확인
- [ ] 수익률 및 보유 현황 확인

### 신호 전환 시

- [ ] Telegram 알림 수신 확인
- [ ] VM 현황 탭에서 주문 결과 확인
- [ ] trade_log.json에 ORDER 항목 기록 확인

### 코드 수정 후 배포

```bash
# 로컬에서
git add 수정한파일.py
git commit -m "설명"
git push

# VM에서
cd /home/hsonic_park/upbit-bot
git pull
sudo systemctl restart upbit-dashboard  # Streamlit 재시작 필요 시
```

### 문제 발생 시

```bash
# 로그 확인
tail -f /home/hsonic_park/upbit-bot/trade.log    # 자동매매 로그
tail -f /home/hsonic_park/upbit-bot/reserve.log  # 예약주문 로그

# Streamlit 로그
sudo journalctl -u upbit-dashboard -f

# 수동으로 테스트 실행
DRY_RUN=true /home/hsonic_park/upbit-venv/bin/python vm_trader.py --mode auto
```

---

## 10. 자주 발생하는 문제와 해결법

### 문제 1: 업비트 API "no_authorization_ip" 오류

**원인:** 로컬 PC IP로 API를 호출함
**해결:** VM IP(`35.209.252.75:8501`)로 접속해야 함. 로컬(`localhost:8501`) 접속 금지

### 문제 2: Streamlit 포트 8501 이미 사용 중

```bash
sudo fuser -k 8501/tcp
sudo systemctl restart upbit-dashboard
```

### 문제 3: cron이 실행되지 않음

```bash
sudo systemctl status cron    # cron 서비스 상태 확인
sudo systemctl start cron     # cron 시작
crontab -l                    # 등록된 cron 목록 확인
```

### 문제 4: git push 실패 (자격증명)

```bash
# PAT(Personal Access Token)으로 remote URL 설정
git remote set-url origin https://사용자명:ghp_토큰값@github.com/사용자명/리포이름.git
```

### 문제 5: VM 현황 탭 데이터 오래됨

- cron이 실행됐는지 확인: `cat trade.log | tail -20`
- VM이 재시작됐는지 확인: `sudo systemctl status cron`
- 수동으로 실행: `DRY_RUN=true python vm_trader.py --mode auto`

### 문제 6: StreamlitDuplicateElementId 오류

버튼/위젯에 `key` 파라미터가 중복됨. 각 위젯에 고유한 key 지정 필요.

### 문제 7: 신호가 계속 SELL인데 매도가 안 됨

신호 전환 시에만 주문이 실행됩니다:
- 이미 SELL 신호였다면 → 유지 (재매도 안 함)
- BUY → SELL 전환 시에만 매도 실행

---

## 마치며

이 시스템은 다음 순서로 발전했습니다:

```
로컬 개발 → GitHub 연동 → VM 배포 → cron 자동화
→ 안정성 강화 → 예약주문 이관 → 모니터링 구축
```

**핵심 교훈:**
1. **IP 보안**: API 허용 IP는 VM만 등록
2. **역할 분리**: VM은 실행, 로컬은 화면만
3. **파일 기반 상태 공유**: 세션 상태(휘발성) 대신 JSON 파일 사용
4. **알림 중요성**: Telegram 없이는 언제 매매됐는지 모름
5. **Dry Run 먼저**: 실제 주문 전 반드시 DRY_RUN=true로 검증

---

*최종 업데이트: 2026-03-30*
*시스템 버전: VM cron + GitHub Actions 백업 구조*
