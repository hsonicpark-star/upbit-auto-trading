"""
Grid Trading Strategy Engine
- 현재가 아래 레벨에만 매수 지정가 주문 등록 (체결 대기)
- 매수 체결 시 그 위 레벨에 자동 매도 주문 생성
- 가격 이탈 시 기존 주문 전체 취소 + 새 기준가로 자동 재설정
"""
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class GridStrategy:
    """
    업비트 그리드 매매 전략 엔진

    Parameters
    ----------
    broker       : BrokerUpbit 인스턴스
    ticker       : 대상 마켓 (예: "KRW-BTC")
    total_invest : 총 투자금액 (KRW)
    grid_count   : 그리드 개수 (상/하단 각각)
    grid_gap_pct : 그리드 간격 비율 (%, 예: 1.0 → 1%)
    upper_limit  : 가격 상단 한계 (None 이면 자동 계산)
    lower_limit  : 가격 하단 한계 (None 이면 자동 계산)
    """

    def __init__(
        self,
        broker,
        ticker: str,
        total_invest: float,
        grid_count: int,
        grid_gap_pct: float,
        upper_limit: float | None = None,
        lower_limit: float | None = None,
    ):
        self.broker = broker
        self.ticker = ticker
        self.total_invest = total_invest
        self.grid_count = grid_count
        self.grid_gap_pct = grid_gap_pct / 100.0          # % → 소수
        self.order_amount = total_invest / grid_count       # 그리드당 주문금액

        self.grids: list[dict] = []                         # 그리드 슬롯 목록
        self.is_running: bool = False
        self.total_profit: float = 0.0                      # 누적 실현 수익 (KRW)
        self.reset_count: int = 0                           # 자동 재설정 횟수
        self.logs: list[dict] = []                          # [{time, msg, level}]

        # 상/하단 한계 (초기화 시 설정)
        self._user_upper = upper_limit
        self._user_lower = lower_limit
        self.upper_limit: float = 0.0
        self.lower_limit: float = 0.0
        self.base_price: float = 0.0

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────

    def _log(self, msg: str, level: str = "INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = {"time": ts, "level": level, "msg": msg}
        self.logs.insert(0, entry)
        if len(self.logs) > 200:
            self.logs = self.logs[:200]
        logger.info("[GridStrategy] %s", msg)

    def _round_price(self, price: float) -> int:
        """업비트 원화 마켓 최소 호가 단위로 반올림"""
        if price >= 2_000_000:
            unit = 1000
        elif price >= 1_000_000:
            unit = 500
        elif price >= 500_000:
            unit = 100
        elif price >= 100_000:
            unit = 50
        elif price >= 10_000:
            unit = 10
        elif price >= 1_000:
            unit = 1
        else:
            unit = 0.1
        return round(round(price / unit) * unit, 1)

    def _volume_for_price(self, price: float) -> float:
        """주문금액 / 가격 → 코인 수량 (소수점 8자리)"""
        if price <= 0:
            return 0.0
        return round(self.order_amount / price, 8)

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def initialize_grids(self, base_price: float | None = None):
        """
        그리드 초기화:
        1. 현재가 기준으로 상/하단 레벨 계산
        2. 현재가 아래 레벨에만 매수 지정가 주문 등록
        3. 현재가 위 레벨은 'empty' 상태로 대기
        """
        if base_price is None or base_price <= 0:
            base_price = self.broker.get_current_price(self.ticker)
        if not base_price or base_price <= 0:
            self._log("현재가 조회 실패 — 초기화 중단", "ERROR")
            return

        self.base_price = float(base_price)
        gap = self.grid_gap_pct

        # 상/하단 한계 계산
        self.upper_limit = self._user_upper or self._round_price(
            self.base_price * (1 + gap * (self.grid_count + 1))
        )
        self.lower_limit = self._user_lower or self._round_price(
            self.base_price * (1 - gap * (self.grid_count + 1))
        )

        # 그리드 레벨 가격 목록 생성
        # level > 0 : 현재가 위 (매도 슬롯)
        # level < 0 : 현재가 아래 (매수 슬롯)
        self.grids = []
        for i in range(1, self.grid_count + 1):
            buy_price  = self._round_price(self.base_price * (1 - gap * i))
            sell_price = self._round_price(self.base_price * (1 + gap * i))

            # 매수 슬롯 (현재가 아래) → 즉시 지정가 주문
            buy_uuid = None
            if buy_price >= self.lower_limit and self.order_amount >= 5000:
                try:
                    res = self.broker.buy_limit_order(
                        self.ticker, buy_price, self._volume_for_price(buy_price)
                    )
                    buy_uuid = res.get("uuid") if isinstance(res, dict) else None
                    self._log(f"매수 주문 등록 레벨-{i}: {buy_price:,}원 (uuid={buy_uuid})")
                except Exception as e:
                    self._log(f"매수 주문 실패 레벨-{i}: {e}", "ERROR")

            self.grids.append({
                "level":        -i,
                "price":        buy_price,
                "side":         "buy",
                "uuid":         buy_uuid,
                "status":       "wait" if buy_uuid else "error",
                "filled_count": 0,
                "profit":       0.0,
            })

            # 매도 슬롯 (현재가 위) → 초기에는 'empty' 상태
            self.grids.append({
                "level":        i,
                "price":        sell_price,
                "side":         "sell",
                "uuid":         None,
                "status":       "empty",
                "filled_count": 0,
                "profit":       0.0,
            })

        # level 순 정렬 (높은 레벨 위로)
        self.grids.sort(key=lambda x: x["level"], reverse=True)

        self._log(
            f"그리드 초기화 완료 | 기준가: {self.base_price:,}원 | "
            f"범위: {self.lower_limit:,}~{self.upper_limit:,}원 | "
            f"그리드: {self.grid_count}개 | 간격: {self.grid_gap_pct*100:.2f}%"
        )
        self.is_running = True

    def check_and_reorder(self):
        """
        미체결 주문 상태 조회 → 체결 감지 → 반대 방향 재주문
        - 매수 체결 → 그 위 레벨(+1 gap)에 매도 주문 등록
        - 매도 체결 → 그 아래 레벨(-1 gap)에 매수 주문 재등록
        """
        if not self.is_running:
            return

        try:
            # 현재 미체결 주문 목록 (uuid 기준으로 상태 확인)
            open_orders = self.broker.get_order(self.ticker, state="wait")
            open_uuids = set()
            if isinstance(open_orders, list):
                open_uuids = {o.get("uuid") for o in open_orders if o.get("uuid")}
        except Exception as e:
            self._log(f"주문 조회 실패: {e}", "ERROR")
            return

        for slot in self.grids:
            uuid = slot.get("uuid")
            if not uuid:
                continue
            if slot["status"] != "wait":
                continue

            # uuid가 미체결 목록에 없으면 → 체결된 것
            if uuid not in open_uuids:
                slot["status"] = "done"
                slot["filled_count"] += 1
                self._log(
                    f"체결 감지 | level={slot['level']} | "
                    f"{slot['side']} @ {slot['price']:,}원"
                )

                if slot["side"] == "buy":
                    # 매수 체결 → 위 레벨에 매도 주문 생성
                    sell_price = self._round_price(
                        slot["price"] * (1 + self.grid_gap_pct)
                    )
                    # 예상 수익 계산 (수수료 0.05% x 2 = 0.1%)
                    fee_rate = 0.001
                    vol = self._volume_for_price(slot["price"])
                    profit = vol * sell_price * (1 - fee_rate) - self.order_amount * (1 + fee_rate)
                    try:
                        res = self.broker.sell_limit_order(self.ticker, sell_price, vol)
                        sell_uuid = res.get("uuid") if isinstance(res, dict) else None
                        # 해당 매도 슬롯 찾아서 업데이트
                        target_level = slot["level"] + (-1 if slot["level"] < 0 else 1)
                        self._update_sell_slot(slot["level"], sell_price, sell_uuid, profit)
                        self._log(f"매도 주문 등록 @ {sell_price:,}원 (예상수익 {profit:+,.0f}원)")
                    except Exception as e:
                        self._log(f"매도 주문 실패: {e}", "ERROR")

                elif slot["side"] == "sell":
                    # 매도 체결 → 수익 실현, 아래 레벨에 매수 재주문
                    self.total_profit += slot.get("profit", 0.0)
                    buy_price = self._round_price(
                        slot["price"] * (1 - self.grid_gap_pct)
                    )
                    vol = self._volume_for_price(buy_price)
                    if self.order_amount >= 5000:
                        try:
                            res = self.broker.buy_limit_order(self.ticker, buy_price, vol)
                            new_uuid = res.get("uuid") if isinstance(res, dict) else None
                            # 이 슬롯을 매수 슬롯으로 재활용
                            slot["side"]   = "buy"
                            slot["price"]  = buy_price
                            slot["uuid"]   = new_uuid
                            slot["status"] = "wait" if new_uuid else "error"
                            slot["profit"] = 0.0
                            self._log(f"매수 재주문 @ {buy_price:,}원")
                        except Exception as e:
                            self._log(f"매수 재주문 실패: {e}", "ERROR")

    def _update_sell_slot(self, buy_level: int, sell_price: float, uuid, profit: float):
        """매수 체결 후 대응하는 매도 슬롯 업데이트"""
        # 매도 슬롯: buy_level의 절댓값이 같고 side=="sell"인 슬롯
        abs_level = abs(buy_level)
        for slot in self.grids:
            if slot["side"] == "sell" and abs(slot["level"]) == abs_level and slot["status"] == "empty":
                slot["uuid"]   = uuid
                slot["status"] = "wait"
                slot["price"]  = sell_price
                slot["profit"] = profit
                return
        # 없으면 새 슬롯 추가
        self.grids.append({
            "level":        abs_level,
            "price":        sell_price,
            "side":         "sell",
            "uuid":         uuid,
            "status":       "wait",
            "filled_count": 0,
            "profit":       profit,
        })
        self.grids.sort(key=lambda x: x["level"], reverse=True)

    def auto_reset_if_out_of_range(self, current_price: float | None = None) -> bool:
        """
        가격이 upper/lower_limit 벗어난 경우 → 전체 취소 + 자동 재설정
        Returns True if reset was triggered.
        """
        if not self.is_running:
            return False
        if current_price is None:
            try:
                current_price = self.broker.get_current_price(self.ticker)
            except Exception:
                return False

        if current_price is None:
            return False

        out_of_range = (
            current_price > self.upper_limit or
            current_price < self.lower_limit
        )
        if not out_of_range:
            return False

        direction = "상단 이탈" if current_price > self.upper_limit else "하단 이탈"
        self._log(
            f"⚠️ 가격 {direction} ({current_price:,}원) → "
            f"범위: {self.lower_limit:,}~{self.upper_limit:,}원 | "
            f"기존 주문 취소 후 재설정",
            "WARNING"
        )
        self.cancel_all(silent=True)
        self.reset_count += 1
        time.sleep(0.5)   # API 레이트 리밋 방지
        self.initialize_grids(base_price=current_price)
        return True

    def cancel_all(self, silent: bool = False):
        """그리드에 등록된 모든 미체결 주문 일괄 취소"""
        cancelled = 0
        for slot in self.grids:
            uuid = slot.get("uuid")
            if uuid and slot["status"] == "wait":
                try:
                    self.broker.cancel_order(uuid)
                    slot["status"] = "cancelled"
                    slot["uuid"]   = None
                    cancelled += 1
                    time.sleep(0.1)   # API 레이트 리밋 방지
                except Exception as e:
                    if not silent:
                        self._log(f"주문 취소 실패 (uuid={uuid}): {e}", "ERROR")
        if not silent:
            self._log(f"주문 전체 취소 완료: {cancelled}건")

    def stop(self):
        """봇 정지 + 미체결 주문 전체 취소"""
        self.cancel_all()
        self.is_running = False
        self._log("그리드 매매 봇 정지")

    def get_status(self) -> dict:
        """UI 렌더링용 상태 dict 반환"""
        current_price = 0.0
        try:
            current_price = self.broker.get_current_price(self.ticker) or 0.0
        except Exception:
            pass

        return {
            "is_running":     self.is_running,
            "ticker":         self.ticker,
            "base_price":     self.base_price,
            "current_price":  current_price,
            "upper_limit":    self.upper_limit,
            "lower_limit":    self.lower_limit,
            "grid_count":     self.grid_count,
            "grid_gap_pct":   self.grid_gap_pct * 100,
            "order_amount":   self.order_amount,
            "total_invest":   self.total_invest,
            "total_profit":   self.total_profit,
            "reset_count":    self.reset_count,
            "grids":          self.grids,
            "logs":           self.logs[:50],
        }
