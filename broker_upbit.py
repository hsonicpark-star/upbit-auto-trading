import pyupbit
import requests
import jwt
import uuid as uuid_mod
import hashlib
from urllib.parse import urlencode


class BrokerUpbit:
    def __init__(self, access, secret):
        self.access_key = access
        self.secret_key = secret
        self.upbit = pyupbit.Upbit(access, secret)
        self.name = "Upbit"

    def _auth_header(self, query=None):
        payload = {
            "access_key": self.access_key,
            "nonce": str(uuid_mod.uuid4()),
        }
        if query:
            query_string = urlencode(query).encode()
            m = hashlib.sha512()
            m.update(query_string)
            payload["query_hash"] = m.hexdigest()
            payload["query_hash_alg"] = "SHA512"
        token = jwt.encode(payload, self.secret_key)
        return {"Authorization": f"Bearer {token}"}

    def get_balances(self):
        return self.upbit.get_balances()

    def get_balance(self, ticker):
        return self.upbit.get_balance(ticker)

    def get_current_price(self, ticker):
        return pyupbit.get_current_price(ticker)

    def get_ohlcv(self, ticker, interval="day", count=200):
        return pyupbit.get_ohlcv(ticker, interval=interval, count=count)

    def get_order(self, ticker, state="wait"):
        return self.upbit.get_order(ticker, state=state)

    def buy_market_order(self, ticker, price):
        return self.upbit.buy_market_order(ticker, price)

    def sell_market_order(self, ticker, volume):
        return self.upbit.sell_market_order(ticker, volume)

    def buy_limit_order(self, ticker, price, volume):
        return self.upbit.buy_limit_order(ticker, price, volume)

    def sell_limit_order(self, ticker, price, volume):
        return self.upbit.sell_limit_order(ticker, price, volume)

    def cancel_order(self, uuid):
        return self.upbit.cancel_order(uuid)

    def get_deposit_history(self, currency="KRW", count=20):
        """입금 내역 조회 (Upbit API v1)"""
        query = {"currency": currency, "limit": count}
        headers = self._auth_header(query)
        try:
            res = requests.get(
                "https://api.upbit.com/v1/deposits",
                params=query, headers=headers, timeout=5,
            )
            if res.status_code == 200:
                return res.json()
        except Exception:
            pass
        return []

    def get_withdraw_history(self, currency="KRW", count=20):
        """출금 내역 조회 (Upbit API v1)"""
        query = {"currency": currency, "limit": count}
        headers = self._auth_header(query)
        try:
            res = requests.get(
                "https://api.upbit.com/v1/withdraws",
                params=query, headers=headers, timeout=5,
            )
            if res.status_code == 200:
                return res.json()
        except Exception:
            pass
        return []
