import os
import requests
import time
import json
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

def get_token(app_key, app_secret, base_url):
    url = f"{base_url}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret
    }
    res = requests.post(url, json=body)
    if res.status_code == 200:
        return res.json().get("access_token")
    else:
        print(f"Token Error: {res.status_code} - {res.text}")
        return None

def test_ohlcv():
    app_key = os.getenv("KIS_REAL_APP_KEY")
    app_secret = os.getenv("KIS_REAL_APP_SECRET")
    base_url = "https://openapi.koreainvestment.com:9443"
    
    token = get_token(app_key, app_secret, base_url)
    if not token:
        print("Failed to get token")
        return

    ticker = "005930" # Samsung
    url = f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHKST03010100",
        "custtype": "P"
    }
    
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=20 * 2)
    
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker,
        "FID_INPUT_DATE_1": start_dt.strftime("%Y%m%d"),
        "FID_INPUT_DATE_2": end_dt.strftime("%Y%m%d"),
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "0"
    }
    
    res = requests.get(url, headers=headers, params=params)
    print(f"Status Code: {res.status_code}")
    if res.status_code == 200:
        data = res.json()
        print(f"Response Keys: {list(data.keys())}")
        if "output2" in data:
            df = pd.DataFrame(data["output2"])
            print(f"Data count: {len(df)}")
            print(df.head())
        else:
            print("output2 not found")
            print(json.dumps(data, indent=2, ensure_ascii=False))
    # 현재가 테스트
    url_price = f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
    headers_price = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHKST01010100",
        "custtype": "P"
    }
    params_price = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker
    }
    res_price = requests.get(url_price, headers=headers_price, params=params_price)
    if res_price.status_code == 200:
        price_data = res_price.json()
        print(f"Current Price (stck_prpr): {price_data.get('output', {}).get('stck_prpr')}")
    else:
        print(f"Price Error: {res_price.text}")

if __name__ == "__main__":
    test_ohlcv()
