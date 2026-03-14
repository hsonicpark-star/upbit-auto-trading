"""
Upbit Auto Trading Bot - Main Entry Point
Volatility Breakout + Moving Average Strategy
"""
import os
import time
import datetime
import pyupbit
from dotenv import load_dotenv
from strategy import get_target_price, get_start_time, check_buy_signal
from utils import setup_logger, get_coin_balance, get_krw_balance, format_price

# 1. Load environment variables and login
load_dotenv()
access = os.getenv("UPBIT_ACCESS_KEY")
secret = os.getenv("UPBIT_SECRET_KEY")
upbit = pyupbit.Upbit(access, secret)

# --- Configuration ---
TICKER = "KRW-BTC"      # Target coin
K_VALUE = 0.5            # Volatility breakout coefficient
MA_PERIOD = 20           # Moving average period
MIN_KRW_ORDER = 5000     # Minimum KRW order amount
MIN_BTC_SELL = 0.00008   # Minimum BTC sell amount

# --- Logger ---
logger = setup_logger()


def run_bot():
    """Main trading loop."""
    logger.info(f"=== {TICKER} Auto Trading Bot Started ===")
    logger.info(f"Strategy: Volatility Breakout (K={K_VALUE}) + MA({MA_PERIOD})")

    while True:
        try:
            now = datetime.datetime.now()
            start_time = get_start_time(TICKER)
            end_time = start_time + datetime.timedelta(days=1)

            # 1. During trading hours (09:00 ~ next day 08:59:50)
            if start_time < now < end_time - datetime.timedelta(seconds=10):
                signal = check_buy_signal(TICKER, K_VALUE, MA_PERIOD)

                logger.info(
                    f"Price: {format_price(signal['current_price'])} | "
                    f"Target: {format_price(signal['target_price'])} | "
                    f"MA{MA_PERIOD}: {format_price(signal['ma_value'])} | "
                    f"Breakout: {signal['breakout']} | "
                    f"Above MA: {signal['above_ma']}"
                )

                # Buy when both conditions are met
                if signal['buy_signal']:
                    krw = get_krw_balance(upbit)
                    if krw > MIN_KRW_ORDER:
                        order_amount = krw * 0.9995  # Fee deduction
                        # upbit.buy_market_order(TICKER, order_amount)  # Uncomment for live trading
                        logger.info(
                            f"BUY SIGNAL! Price: {format_price(signal['current_price'])} | "
                            f"Amount: {format_price(order_amount)} KRW"
                        )

            # 2. Before market close (08:59:50 ~ 09:00:00) - Sell all
            else:
                btc_balance = get_coin_balance(upbit, TICKER)
                if btc_balance > MIN_BTC_SELL:
                    # upbit.sell_market_order(TICKER, btc_balance)  # Uncomment for live trading
                    logger.info(f"SELL ALL! Balance: {btc_balance:.8f} BTC")

            time.sleep(1)

        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(1)


if __name__ == "__main__":
    run_bot()
