# VM 중심 자동매매 시스템 - 구현 완료 보고

## 구현 결과

### 생성된 파일

| 파일 | 역할 |
|------|------|
| [vm_trader.py](file:///d:/05.%EC%9E%90%EB%8F%99%ED%99%94%EA%B5%90%EC%9C%A1/12.API/%EC%97%85%EB%B9%84%ED%8A%B8%20%EC%9E%90%EB%8F%99%EB%A7%A4%EB%A7%A4%20%EA%B3%B5%EC%9C%A0/vm_trader.py) | VM 트레이딩 엔진 (Donchian+SMA 전략, 주문 실행) |
| [.github/workflows/auto_trade.yml](file:///d:/05.%EC%9E%90%EB%8F%99%ED%99%94%EA%B5%90%EC%9C%A1/12.API/%EC%97%85%EB%B9%84%ED%8A%B8%20%EC%9E%90%EB%8F%99%EB%A7%A4%EB%A7%A4%20%EA%B3%B5%EC%9C%A0/.github/workflows/auto_trade.yml) | GitHub Actions 스케줄러 (4시간 주기) |
| [tabs/tab_vm_status.py](file:///d:/05.%EC%9E%90%EB%8F%99%ED%99%94%EA%B5%90%EC%9C%A1/12.API/%EC%97%85%EB%B9%84%ED%8A%B8%20%EC%9E%90%EB%8F%99%EB%A7%A4%EB%A7%A4%20%EA%B3%B5%EC%9C%A0/tabs/tab_vm_status.py) | Streamlit 읽기 전용 탭 |
| [data/](file:///d:/05.%EC%9E%90%EB%8F%99%ED%99%94%EA%B5%90%EC%9C%A1/12.API/%EC%97%85%EB%B9%84%ED%8A%B8%20%EC%9E%90%EB%8F%99%EB%A7%A4%EB%A7%A4%20%EA%B3%B5%EC%9C%A0/vm_trader.py#55-57) 디렉토리 | JSON 상태 파일 저장소 |

---

## Dry Run 검증 결과

```
DRY_RUN=true python vm_trader.py --mode auto
```

**성공**: JSON 3개 파일 정상 생성

### signal_state.json 결과
```json
{
  "ticker": "KRW-BTC",
  "signal": "SELL",
  "current_price": 100730000.0,
  "donchian_upper": 112450000.0,
  "donchian_lower": 99952000.0,
  "sma": 102932310.34,
  "updated_at": "2026-03-28 13:48:44 KST"
}
```
> 현재가(100,730,000) < SMA29(102,932,310) → **SELL** 신호

### trade_log.json 결과
```json
[{"ts": "2026-03-28 13:48:44 KST", "type": "RUN", "signal": "SELL", "dry_run": true}]
```

---

## 다음 설정 단계 (사용자 수행 필요)

### 1. GitHub Secrets 등록
GitHub 리포지토리 → Settings → Secrets → Actions에서 추가:
- `UPBIT_ACCESS_KEY`
- `UPBIT_SECRET_KEY`

### 2. tab_vm_status.py URL 수정
[tabs/tab_vm_status.py](file:///d:/05.%EC%9E%90%EB%8F%99%ED%99%94%EA%B5%90%EC%9C%A1/12.API/%EC%97%85%EB%B9%84%ED%8A%B8%20%EC%9E%90%EB%8F%99%EB%A7%A4%EB%A7%A4%20%EA%B3%B5%EC%9C%A0/tabs/tab_vm_status.py) 상단의 `GITHUB_RAW_BASE` 변수를 실제 리포 정보로 수정:
```python
GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/"
    "실제GitHub사용자명/실제리포이름/main/data"
)
```

### 3. data/ 파일 첫 커밋 후 GitHub Actions 수동 트리거
```bash
git add data/
git commit -m "feat: add initial trading data files"
git push

# GitHub → Actions → "Auto Trade (Upbit)" → Run workflow
```

### 4. 실제 거래 활성화 (준비 완료 시)
GitHub Actions에서 `workflow_dispatch` 수동 실행 시 `dry_run` 입력값을 `false`로 변경.

---

## 아키텍처 요약

```
[GitHub Actions – 4시간 주기]
           ↓
    [VM: vm_trader.py]
    ├─ 잔고 조회 (Upbit API)
    ├─ Donchian(115/105, 4H) + SMA(29, 1D) 계산
    ├─ 신호 전환 시 주문 실행 (DRY_RUN=false일 때)
    └─ data/*.json 저장 → GitHub 커밋

[로컬 Streamlit]
    └─ GitHub Raw URL에서 JSON 읽기 → "🖥️ VM 현황" 탭 표시
       (로컬 PC 꺼져도 VM 독립 작동)
```
