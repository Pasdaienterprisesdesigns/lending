import os
from datetime import datetime, timedelta
import requests
import pandas as pd
import streamlit as st

# ─── CONFIG ─────────────────────────────────────────────────────────────────────
SIM_API_KEY = os.getenv("SIM_API_KEY") or "sim_444cGnNxG0exoklzAjwNsmIGcv03PBDG"
SIM_BASE    = "https://api.sim.dune.com/v1/evm"
HEADERS     = {"X-Sim-Api-Key": SIM_API_KEY}

# ─── HELPERS ────────────────────────────────────────────────────────────────────
def fetch_gas_data(start: datetime, end: datetime, limit: int = 500) -> pd.DataFrame:
    """
    Fetch transactions between start and end, return DataFrame with gas price (gwei) indexed by timestamp.
    """
    rows = []
    params = {
        "limit": limit,
        "since": start.isoformat() + "Z",
        "until": end.isoformat() + "Z"
    }
    offset = None
    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(
            f"{SIM_BASE}/transactions/0x0000000000000000000000000000000000000000",
            headers=HEADERS,
            params=params,
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        txs = data.get("transactions", [])
        for t in txs:
            gp_hex = t.get("gas_price") or t.get("max_fee_per_gas")
            if not gp_hex:
                continue
            gp = int(gp_hex, 16) / 1e9
            rows.append({"ts": pd.to_datetime(t["block_time"]), "gas": gp})
        offset = data.get("next_offset")
        if not offset or len(txs) < limit:
            break
    df = pd.DataFrame(rows).set_index("ts").sort_index()
    return df

# ─── FORECASTS ─────────────────────────────────────────────────────────────────
def compute_forecasts(df: pd.DataFrame):
    """
    Given raw gas series, resample into 10-min bins and compute:
      - Next 10-min forecast (30th percentile over past 6h)
      - Next 6h forecast (30th percentile over past 36h)
    """
    s10 = df["gas"].resample("10min").mean().dropna()
    forecast_10min = s10.rolling(window=36).quantile(0.3).iloc[-1]
    forecast_6h = s10.rolling(window=36 * 6).quantile(0.3).iloc[-1]
    return s10, forecast_10min, forecast_6h

# ─── TIME-OF-DAY ANALYSIS ───────────────────────────────────────────────────────
def cheapest_time_of_day(df: pd.DataFrame):
    """
    Over the last month, find the hour of day (0-23 UTC) with the lowest average gas price.
    """
    s_hour = df["gas"].resample("1h").mean().dropna()
    hourly = s_hour.groupby(s_hour.index.hour).mean().sort_index()
    best_hour = int(hourly.idxmin())
    avg_price = float(hourly.min())
    return best_hour, avg_price, hourly

# ─── STREAMLIT UI ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Gas Fee Forecast & Optimizer", layout="centered")
st.title("⛽ Gas Fee Forecast & Optimizer")

if st.button("Run Forecast"):
    now = datetime.utcnow()
    # fetch last 6h for reliable 10-min forecasts
    df_recent = fetch_gas_data(now - timedelta(hours=6), now)
    # fetch last 30d for hourly-of-day analysis
    df_month = fetch_gas_data(now - timedelta(days=30), now)

    _, f10, f6 = compute_forecasts(df_recent)
    st.metric("Next 10-min forecast (30th pct)", f"{f10:.2f} gwei")
    st.metric("Next 6h forecast (30th pct)", f"{f6:.2f} gwei")

    best_hr, avg_p, hourly = cheapest_time_of_day(df_month)
    st.write(f"Cheapest hour in last 30d: **{best_hr}:00 UTC**, avg {avg_p:.2f} gwei")

    st.subheader("Hourly Average Gas Price (Last 30 Days)")
    st.bar_chart(hourly)
else:
    st.write("Click **Run Forecast** to compute gas predictions and view hourly averages.")
