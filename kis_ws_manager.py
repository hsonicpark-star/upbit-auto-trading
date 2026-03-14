import websocket
import json
import threading
import time
import requests
import logging

class KisOrderbookManager:
    _instance = None
    _lock = threading.Lock()

    app_key = None
    app_secret = None
    mock = False
    ws = None
    ws_thread = None
    running = False
    current_ticker = None
    approval_key = None
    base_url = ""
    ws_url = ""
    latest_data = {}
    data_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(KisOrderbookManager, cls).__new__(cls)
                cls._instance._init_once()
            return cls._instance

    def _init_once(self):
        self.app_key = None
        self.app_secret = None
        self.mock = False
        
        self.ws = None
        self.ws_thread = None
        self.running = False
        self.current_ticker = None
        
        self.approval_key = None
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.ws_url = "ws://ops.koreainvestment.com:21000"
        
        self.latest_data = {}
        self.data_lock = threading.Lock()

    def set_credentials(self, app_key, app_secret, mock=False):
        self.app_key = app_key
        self.app_secret = app_secret
        self.mock = mock
        self.base_url = "https://openapivts.koreainvestment.com:29443" if mock else "https://openapi.koreainvestment.com:9443"
        self.ws_url = "ws://ops.koreainvestment.com:31000" if mock else "ws://ops.koreainvestment.com:21000"
        logging.info(f"KIS WS Credentials set: mock={mock}, ws_url={self.ws_url}")

    def _get_approval_key(self):
        """웹소켓 접속을 위한 approval_key 발급"""
        if self.approval_key:
            return self.approval_key
            
        url = f"{self.base_url}/oauth2/Approval"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "secretkey": self.app_secret
        }
        try:
            res = requests.post(url, json=body)
            if res.status_code == 200:
                self.approval_key = res.json().get("approval_key")
                return self.approval_key
            else:
                logging.error(f"KIS WS Approval Key Error: {res.text}")
                return None
        except Exception as e:
            logging.error(f"KIS WS Approval Key Exception: {e}")
            return None

    def subscribe(self, ticker):
        code = ticker.replace("KRW-", "") if ticker.startswith("KRW-") else ticker
        
        with self.data_lock:
            if self.current_ticker == code and self.running:
                return
            self.current_ticker = code
            self.latest_data = {}

        self.stop()
        self.running = True
        self.ws_thread = threading.Thread(target=self._run_ws, args=(code,), daemon=True)
        self.ws_thread.start()
        logging.info(f"KIS WS Subscribing to: {code}")

    def _run_ws(self, code):
        approval_key = self._get_approval_key()
        if not approval_key:
            logging.error("Failed to get KIS WS approval key. Cannot start websocket.")
            return
            
        def on_message(ws, message):
            if message.startswith("0") or message.startswith("1"):
                # 실시간 데이터 파싱 (|로 구분됨)
                parts = message.split("|")
                if len(parts) >= 4:
                    tr_id = parts[1]
                    data_str = parts[3]
                    
                    if tr_id == "H0STASP0": # 국내주식 실시간 호가
                        self._parse_orderbook(data_str)
                    elif tr_id == "H0STCNT0": # 국내주식 실시간 체결 (추후 확장용)
                        pass

        def on_error(ws, error):
            logging.error(f"KIS WS Error: {error}")

        def on_close(ws, close_status_code, close_msg):
            logging.info(f"KIS WS Closed: {close_status_code} - {close_msg}")

        def on_open(ws):
            logging.info("KIS WS Connected. Sending subscription request...")
            req = {
                "header": {
                    "approval_key": approval_key,
                    "custtype": "P",
                    "tr_type": "1",
                    "content-type": "utf-8"
                },
                "body": {
                    "input": {
                        "tr_id": "H0STASP0", # 실시간 호가
                        "tr_key": code
                    }
                }
            }
            ws.send(json.dumps(req))

        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        while self.running:
            self.ws.run_forever(ping_interval=60)
            if self.running:
                logging.info("KIS WS reconnecting in 5 seconds...")
                time.sleep(5)

    def stop(self):
        self.running = False
        if self.ws:
            self.ws.close()
            self.ws = None
        if self.ws_thread and self.ws_thread.is_alive():
            # join()을 사용하면 block될 수 있으므로 flag만 끄고 자연스럽게 종료 유도
            pass
            
    def _parse_orderbook(self, data_str):
        """KIS 호가 데이터(H0STASP0) 파싱"""
        fields = data_str.split("^")
        if len(fields) < 50:
            return
            
        # KIS H0STASP0 포맷 (매도호가 10개, 매수호가 10개, 매도잔량 10개, 매수잔량 10개 순)
        # 0: 종목코드, 1: 시간, 2: 구분... 
        # 3~12: 매도호가1~10
        # 13~22: 매수호가1~10
        # 23~32: 매도잔량1~10
        # 33~42: 매수잔량1~10
        
        units = []
        try:
            for i in range(10):
                ask_price = float(fields[3 + i])
                bid_price = float(fields[13 + i])
                ask_size = float(fields[23 + i])
                bid_size = float(fields[33 + i])
                
                units.append({
                    "ask_price": ask_price,
                    "bid_price": bid_price,
                    "ask_size": ask_size,
                    "bid_size": bid_size
                })
                
            total_ask_size = float(fields[43])
            total_bid_size = float(fields[44])
            
            parsed = {
                "total_ask_size": total_ask_size,
                "total_bid_size": total_bid_size,
                "orderbook_units": units,
                "timestamp": time.time()
            }
            
            with self.data_lock:
                self.latest_data = parsed
        except Exception as e:
            # logging.debug(f"KIS parse error: {e}")
            pass

    def get_orderbook(self):
        with self.data_lock:
            return self.latest_data

kis_ws_manager = KisOrderbookManager()
