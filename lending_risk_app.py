import os
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
import plotly.express as px
from web3 import Web3

# ─── CONFIG ─────────────────────────────────────────────────────────────────────
RPC_URL       = "https://mainnet.infura.io/v3/6998b5202d9e41339c5dea660a21412a"
WEB3_HTTP     = Web3(Web3.HTTPProvider(RPC_URL))
WEB3_WS       = Web3(Web3.WebsocketProvider(RPC_URL.replace('https','wss')))
HIST_DAYS     = 30
BLOCK_TIME_S  = 12  # average block time in seconds
BLOCKS_PER_HR = int(3600 / BLOCK_TIME_S)
HOURS_30D     = HIST_DAYS * 24

st.set_page_config(page_title="Gas‐Fee ML Explorer", layout="centered")
st.title("🔮 Gas-Fee Time-of-Day & 10-Minute Forecast")

@st.cache_data(ttl=3600)
def fetch_30d_hourly():
    """
    Backfill last 30 days hourly baseFeePerGas via JSON-RPC.
    """
    latest_block = WEB3_HTTP.eth.block_number
    rows = []
    for i in range(HOURS_30D):
        blk_num = latest_block - i * BLOCKS_PER_HR
        if blk_num < 0:
            break
        bl = WEB3_HTTP.eth.get_block(blk_num)
        ts = datetime.utcfromtimestamp(bl.timestamp)
        # baseFeePerGas is in wei
        base_fee = bl.baseFeePerGas / 1e9  # gwei
        rows.append({"dt": ts, "baseFee": base_fee})
    df = pd.DataFrame(rows)
    df.set_index('dt', inplace=True)
    return df.sort_index()

@st.cache_data(ttl=300)
def fetch_10min_history():
    """
    Fetch last 10 minutes of blocks and compute 30th percentile baseFee.
    """
    block_count = int((10 * 60) / BLOCK_TIME_S)
    fh = WEB3_HTTP.eth.fee_history(
        block_count=block_count,
        newest_block='latest',
        reward_percentiles=[]
    )
    # skip the first entry (oldest), use the rest
    raw_fees = fh['baseFeePerGas'][1:]
    gwei = [b / 1e9 for b in raw_fees]
    return pd.Series(gwei).quantile(0.3)

# ─── MAIN ───────────────────────────────────────────────────────────────────────
# 1) Load 30-day hourly history
df_30d = fetch_30d_hourly()

# 2) Compute time-of-day stats
hourly_avg = df_30d['baseFee'].groupby(df_30d.index.hour).mean()
best_hour = int(hourly_avg.idxmin())
avg_price = float(hourly_avg.min())

# 3) Train a simple regression model
from sklearn.ensemble import RandomForestRegressor
# Feature engineer
df_30d['hour'] = df_30d.index.hour
df_30d['dow']  = df_30d.index.dayofweek
X = df_30d[['hour','dow']]
y = df_30d['baseFee']
model = RandomForestRegressor(n_estimators=100)
model.fit(X, y)

# 4) Predict next 10-min
now = datetime.utcnow()
feat = pd.DataFrame([{'hour': now.hour, 'dow': now.weekday()}])
pred_10 = model.predict(feat)[0]
# override with direct 30th percentile if desired
pct30_10 = fetch_10min_history()

# ─── STREAMLIT OUTPUT ─────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
col1.metric("Cheapest Hour (Last 30d)", f"{best_hour:02d}:00 UTC", delta=f"{avg_price:.2f} gwei")
col2.metric("10-min Forecast (ML)", f"{pred_10:.2f} gwei", delta=f"30th pct: {pct30_10:.2f} gwei")

st.subheader("Hourly Average BaseFee (Last 30 Days)")
fig = px.bar(
    x=hourly_avg.index,
    y=hourly_avg.values,
    labels={'x':'Hour (UTC)','y':'Avg BaseFee (gwei)'},
    title='Avg Gas Price by Hour of Day'
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("30-Day BaseFee Time Series")
fig2 = px.line(df_30d, y='baseFee', labels={'dt':'Date','baseFee':'BaseFee (gwei)'})
st.plotly_chart(fig2, use_container_width=True)
