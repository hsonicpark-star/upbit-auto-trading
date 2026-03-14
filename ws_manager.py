import threading
import time
import pyupbit
import logging

class OrderbookManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(OrderbookManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.current_ticker = None
        self.wm = None
        self.ws_thread = None
        self.running = False
        self.latest_orderbook = {}
        self.data_lock = threading.Lock()

    def subscribe(self, ticker: str):
        """구독할 티커를 변경합니다."""
        if self.current_ticker == ticker:
            return # 이미 구독중

        self.current_ticker = ticker
        
        # 기존 스레드 및 웹소켓 정리
        self.stop()
        
        # 새 웹소켓 매니저 시작
        self.running = True
        self.wm = pyupbit.WebSocketManager("orderbook", [ticker])
        self.ws_thread = threading.Thread(target=self._run, daemon=True)
        self.ws_thread.start()
        logging.info(f"[WS] {ticker} 오더북 구독 시작")

    def _run(self):
        while self.running and self.wm is not None:
            try:
                # get()은 블로킹 호출입니다.
                data = self.wm.get()
                if not self.running:
                    break
                if data and "orderbook_units" in data:
                    with self.data_lock:
                        self.latest_orderbook = data
            except Exception as e:
                logging.error(f"[WS] 오더북 수신 에러: {e}")
                time.sleep(1)

    def get_orderbook(self):
        """가장 최근에 수신된 오더북 데이터를 반환합니다."""
        with self.data_lock:
            return self.latest_orderbook.copy()

    def stop(self):
        self.running = False
        if self.wm:
            try:
                self.wm.terminate()
            except:
                pass
            self.wm = None
        if self.ws_thread and self.ws_thread.is_alive():
            # get() 블로킹을 풀기 위해 기다리지 않고 데몬으로 둠
            pass

# 싱글톤 인스턴스 전역 접근점
ob_manager = OrderbookManager()
