#!/bin/bash
cd ~/upbit-auto-trading
pkill -f streamlit || true
sleep 2
source venv/bin/activate
nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 > streamlit.log 2>&1 &
echo "Started Streamlit in background"
sleep 2
