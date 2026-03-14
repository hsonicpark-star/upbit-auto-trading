import os
import time
import requests
import json
import logging
from datetime import datetime
import pandas as pd

class BrokerKIS:
    def __init__(self, app_key, app_secret, account_number, mock=False):
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_number = account_number
        self.mock = mock
        self.name = "한국투자증권(모의)" if mock else "한국투자증권(실전)"
        
        self.base_url = "https://openapivts.koreainvestment.com:29443" if mock else "https://openapi.koreainvestment.com:9443"
        self.access_token = ""
        self.token_expired_at = 0
        
        # 계좌번호 포맷 강제 ('-01'이 없으면 추가)
        if "-" not in self.account_number:
            self.account_number += "-01"
            
        self._acc_no_prefix = self.account_number.split("-")[0]
        self._acc_no_postfix = self.account_number.split("-")[1]
        
    def _get_token(self):
        now = time.time()
        if self.access_token and now < self.token_expired_at:
            return self.access_token
            
        url = f"{self.base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        res = requests.post(url, json=body)
        if res.status_code == 200:
            data = res.json()
            self.access_token = data.get("access_token")
            # expires_in is usually 86400 (1 day)
            self.token_expired_at = now + data.get("expires_in", 86400) - 60
            return self.access_token
        else:
            logging.error(f"KIS Token Error: {res.text}")
            return None

    def _headers(self, tr_id, tr_cont=""):
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._get_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "tr_cont": tr_cont,
            "custtype": "P"
        }

    def get_balances(self):
        """
        주식 잔고 및 예수금 통합 조회
        MCP 패턴에 따라 페이지네이션(tr_cont) 처리 지원
        """
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "VTTC8434R" if self.mock else "TTTC8434R"
        
        all_holdings = []
        krw_balance = 0.0
        
        tr_cont = ""
        ctx_fk = ""
        ctx_nk = ""
        
        while True:
            params = {
                "CANO": self._acc_no_prefix,
                "ACNT_PRDT_CD": self._acc_no_postfix,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": ctx_fk,
                "CTX_AREA_NK100": ctx_nk
            }
            
            headers = self._headers(tr_id, tr_cont)
            res = requests.get(url, headers=headers, params=params)
            
            if res.status_code != 200:
                logging.error(f"KIS Balance Error: {res.text}")
                break
                
            data = res.json()
            if data.get("rt_cd") != "0":
                logging.error(f"KIS Balance Logic Error: {data.get('msg1')}")
                break
            
            # 1. 예수금 (첫 페이지에서만 혹은 공통으로 합산)
            if "output2" in data and len(data["output2"]) > 0:
                # dnca_tot_amt: 예수금총금액
                krw_balance = float(data["output2"][0].get("dnca_tot_amt", 0))
            
            # 2. 보유 주식
            if "output1" in data:
                all_holdings.extend(data["output1"])
            
            # 페이지네이션 확인
            tr_cont = res.headers.get("tr_cont", "")
            if tr_cont not in ["M", "F"]:
                break
                
            ctx_fk = data.get("ctx_area_fk100", "")
            ctx_nk = data.get("ctx_area_nk100", "")
            time.sleep(0.1) # 과부하 방지
            
        # Upbit 포맷으로 변환
        balances = [{"currency": "KRW", "balance": krw_balance, "locked": 0.0}]
        for item in all_holdings:
            code = item.get("pdno")
            qty = float(item.get("hldg_qty", 0))
            ord_psbl = float(item.get("ord_psbl_qty", qty))
            if qty > 0:
                balances.append({
                    "currency": code,
                    "balance": qty,
                    "locked": max(0.0, qty - ord_psbl)
                })
        return balances

    def get_balance(self, ticker):
        code = ticker.replace("KRW-", "") if ticker.startswith("KRW-") else ticker
        balances = self.get_balances()
        for b in balances:
            if b["currency"] == code:
                return b["balance"]
        return 0.0

    def get_current_price(self, ticker):
        code = ticker.replace("KRW-", "") if ticker.startswith("KRW-") else ticker
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        # MCP 가이드에 따른 현재가 시세 TR_ID
        headers = self._headers("FHKST01010100")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code
        }
        
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            data = res.json()
            if "output" in data:
                # stck_prpr: 주식 현재가
                return float(data["output"]["stck_prpr"])
        return 0.0

    def get_ohlcv(self, ticker, interval="day", count=200):
        """
        KIS Ohlcv 조회 - 사용자의 요청에 따라 무조건 일봉으로 처리
        최대 100건까지 조회 가능하므로 count가 100을 넘으면 100으로 제한 (단일 호출 기준)
        """
        code = ticker.replace("KRW-", "") if ticker.startswith("KRW-") else ticker
        
        # 일봉(day) 조회 - 주식 일별 차트 조회 (FHKST01010400) 가 더 안정적임
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        headers = self._headers("FHKST01010400") # 01010400으로 변경
        
        from datetime import timedelta
        end_dt = datetime.now()
        # 최근 100건을 가져오기 위해 150일 전부터 조회 (영업일 고려)
        start_dt = end_dt - timedelta(days=150)
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code,
            "FID_INPUT_DATE_1": start_dt.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": end_dt.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0"      # 0: 수정주가
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 200:
                data = res.json()
                output2 = data.get("output2", [])
                if not output2:
                    logging.warning(f"KIS OHLCV No Data: {data.get('msg1')}")
                    return pd.DataFrame()
                
                # 모든 키를 소문자로 정규화 (KIS는 가끔 대문자 짬뽕으로 리턴함)
                normalized_data = []
                for entry in output2:
                    normalized_data.append({k.lower(): v for k, v in entry.items()})
                
                df = pd.DataFrame(normalized_data)
                
                # 컬럼 매핑
                # stck_clpr: 종가, stck_oprc: 시가, stck_hgpr: 고가, stck_lwpr: 저가, acml_vol: 거래량
                df = df.rename(columns={
                    "stck_oprc": "open",
                    "stck_hgpr": "high",
                    "stck_lwpr": "low",
                    "stck_clpr": "close",
                    "acml_vol": "volume"
                })
                
                # 수치형 변환
                for col in ["open", "high", "low", "close", "volume"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # 날짜 인덱스 설정
                if "stck_bsop_date" in df.columns:
                    df['stck_bsop_date'] = pd.to_datetime(df['stck_bsop_date'], format='%Y%m%d', errors='coerce')
                    df = df.dropna(subset=['stck_bsop_date']).set_index('stck_bsop_date').sort_index()
                
                return df.tail(count)
            else:
                logging.error(f"KIS OHLCV HTTP Error: {res.status_code} - {res.text}")
        except Exception as e:
            logging.error(f"KIS OHLCV Exception: {e}")
            
        return pd.DataFrame()

    def get_order(self, ticker, state="wait"):
        """
        주문 조회 - state에 따라 다른 API 호출
        state='wait' → 미체결(취소가능) 조회 (inquire-psbl-rvsecncl)
        state='done'/'cancel' → 일별 체결 내역 조회 (inquire-daily-ccld)
        """
        code = ticker.replace("KRW-", "") if ticker.startswith("KRW-") else ticker

        if state in ("done", "cancel"):
            return self._get_daily_ccld(code, state)

        # 미체결 조회
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
        tr_id = "VTTC8036R" if self.mock else "TTTC8036R"
        headers = self._headers(tr_id)
        params = {
            "CANO": self._acc_no_prefix,
            "ACNT_PRDT_CD": self._acc_no_postfix,
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
            "INQR_DVSN_1": "1",
            "INQR_DVSN_2": "0"
        }
        res = requests.get(url, headers=headers, params=params)
        orders = []
        if res.status_code == 200:
            data = res.json()
            if "output" in data:
                for item in data["output"]:
                    item_code = item.get("pdno")
                    if ticker and code != item_code:
                        continue

                    orders.append({
                        "uuid": item.get("odno"),
                        "side": "bid" if item.get("sll_buy_dvsn_cd") == "02" else "ask",
                        "ord_type": "limit",
                        "price": float(item.get("ord_unpr", 0)),
                        "state": "wait",
                        "market": item_code,
                        "created_at": item.get("ord_dt") + " " + item.get("ord_tmd"),
                        "volume": float(item.get("ord_qty", 0)),
                        "executed_volume": float(item.get("tot_ccld_qty", 0))
                    })
        return orders

    def _get_daily_ccld(self, code, state="done"):
        """
        일별 주문체결 조회 (v1_국내주식-005)
        TR_ID: TTTC8001R(실전) / VTTC8001R(모의)
        """
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
        tr_id = "VTTC8001R" if self.mock else "TTTC8001R"

        end_dt = datetime.now()
        start_dt = end_dt - pd.Timedelta(days=30)

        all_orders = []
        ctx_fk = ""
        ctx_nk = ""
        tr_cont = ""

        while True:
            headers = self._headers(tr_id, tr_cont)
            params = {
                "CANO": self._acc_no_prefix,
                "ACNT_PRDT_CD": self._acc_no_postfix,
                "INQR_STRT_DT": start_dt.strftime("%Y%m%d"),
                "INQR_END_DT": end_dt.strftime("%Y%m%d"),
                "SLL_BUY_DVSN_CD": "00",
                "INQR_DVSN": "00",
                "PDNO": "",
                "CCLD_DVSN": "01" if state == "done" else "02",
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "INQR_DVSN_3": "00",
                "INQR_DVSN_1": "",
                "CTX_AREA_FK100": ctx_fk,
                "CTX_AREA_NK100": ctx_nk,
            }

            res = requests.get(url, headers=headers, params=params)
            if res.status_code != 200:
                logging.error(f"KIS Daily CCLD Error: {res.text}")
                break

            data = res.json()
            if data.get("rt_cd") != "0":
                logging.error(f"KIS Daily CCLD Logic Error: {data.get('msg1')}")
                break

            if "output1" in data:
                for item in data["output1"]:
                    item_code = item.get("pdno", "")
                    if code and code != item_code:
                        continue

                    ccld_qty = float(item.get("tot_ccld_qty", 0))
                    avg_price = float(item.get("avg_prvs", 0))

                    all_orders.append({
                        "uuid": item.get("odno", ""),
                        "side": "bid" if item.get("sll_buy_dvsn_cd") == "02" else "ask",
                        "ord_type": "limit" if item.get("ord_dvsn_cd") == "00" else "market",
                        "price": avg_price,
                        "state": "done" if ccld_qty > 0 else "wait",
                        "market": item_code,
                        "created_at": f"{item.get('ord_dt', '')} {item.get('ord_tmd', '')[:6]}",
                        "volume": float(item.get("ord_qty", 0)),
                        "executed_volume": ccld_qty,
                        "paid_fee": 0.0,
                    })

            tr_cont = res.headers.get("tr_cont", "")
            if tr_cont not in ["M", "F"]:
                break
            ctx_fk = data.get("ctx_area_fk100", "")
            ctx_nk = data.get("ctx_area_nk100", "")
            time.sleep(0.1)

        return all_orders
        
    def _order(self, ticker, price, volume, side, ord_type):
        """
        주식주문(현금) (v1_국내주식-001)
        MCP 권장 TR_ID 및 파라미터 적용
        """
        code = ticker.replace("KRW-", "") if ticker.startswith("KRW-") else ticker
        
        # MCP 가이드에 따른 TR_ID (TTTC0011U: 매도, TTTC0012U: 매수)
        if self.mock:
            tr_id = "VTTC0012U" if side == "bid" else "VTTC0011U"
        else:
            tr_id = "TTTC0012U" if side == "bid" else "TTTC0011U"
            
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        headers = self._headers(tr_id)
        
        # 00: 지정가, 01: 시장가
        ord_dvsn = "01" if ord_type == "market" else "00"
        
        body = {
            "CANO": self._acc_no_prefix,
            "ACNT_PRDT_CD": self._acc_no_postfix,
            "PDNO": code,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(int(volume)),
            "ORD_UNPR": str(int(price)) if ord_dvsn == "00" else "0"
        }
        
        res = requests.post(url, headers=headers, json=body)
        if res.status_code == 200:
            data = res.json()
            if data.get("rt_cd") == "0":
                return {"uuid": data.get("output", {}).get("ODNO"), "msg": data.get("msg1")}
            else:
                logging.error(f"KIS Order Error: {data.get('msg1')}")
                return None
        return None

    def buy_market_order(self, ticker, price_krw):
        curr_price = self.get_current_price(ticker)
        if curr_price == 0: return None
        qty = int(price_krw / curr_price)
        if qty <= 0: return None
        return self._order(ticker, 0, qty, "bid", "market")

    def sell_market_order(self, ticker, volume):
        return self._order(ticker, 0, volume, "ask", "market")

    def buy_limit_order(self, ticker, price, volume):
        return self._order(ticker, price, volume, "bid", "limit")

    def sell_limit_order(self, ticker, price, volume):
        return self._order(ticker, price, volume, "ask", "limit")

    def cancel_order(self, uuid):
        """주문취소/정정 (v1_국내주식-003)"""
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-rvsecncl"
        tr_id = "VTTC0803U" if self.mock else "TTTC0803U"
        headers = self._headers(tr_id)
        
        body = {
            "CANO": self._acc_no_prefix,
            "ACNT_PRDT_CD": self._acc_no_postfix,
            "KRX_FWDG_ORD_ORGNO": "", 
            "ORGN_ODNO": uuid,
            "ORD_DVSN": "00",
            "RVSE_CNCL_DVSN_CD": "02", # 02: 취소
            "ORD_QTY": "0",
            "ORD_UNPR": "0",
            "QTY_ALL_ORD_YN": "Y"
        }
        
        res = requests.post(url, headers=headers, json=body)
        if res.status_code == 200:
            data = res.json()
            if data.get("rt_cd") == "0":
                return True
        return False
