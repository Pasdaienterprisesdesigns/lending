import os
from datetime import datetime, timezone
import requests
import pandas as pd
import streamlit as st
from sklearn.ensemble import IsolationForest

# ─── Optional Auto-Refresh ────────────────────────────────────────────────────
try:
    from streamlit_autorefresh import st_autorefresh  # type: ignore
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

# ─── Configuration ─────────────────────────────────────────────────────────────
SIM_API_KEY    = os.getenv("SIM_API_KEY") or "sim_444cGnNxG0exoklzAjwNsmIGcv03PBDG"
if not SIM_API_KEY:
    st.error("Please set the SIM_API_KEY environment variable.")
    st.stop()

API_BASE       = "https://api.sim.dune.com/v1/evm"
HEADERS        = {"X-Sim-Api-Key": SIM_API_KEY, "Content-Type": "application/json"}
PLATFORMS      = ["aave", "compound"]
CHAIN_ID       = 1  # 1 = Ethereum Mainnet; change as needed for other EVM chains
WINDOW_MINUTES = 1
REFRESH_MS     = 60_000
CONTAMINATION  = 0.01

# ─── Auto-refresh setup ─────────────────────────────────────────────────────────
if HAS_AUTOREFRESH:
    st_autorefresh(interval=REFRESH_MS, key="auto_refresh")

st.set_page_config(page_title="💰 DeFi Lending Risk Analyzer", layout="wide")
st.title("💰 DeFi Lending Risk Analyzer")

wallet = st.text_input("Wallet address (0x...)", "")
if not wallet:
    st.info("Enter an Ethereum wallet to analyze.")
    st.stop()

# ─── Fetching helpers ───────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch_lending_positions(wallet: str) -> pd.DataFrame:
    dfs = []
    for proto in PLATFORMS:
        url = f"{API_BASE}/lending-positions/{wallet}"
        params = {"protocol": proto, "chain_id": CHAIN_ID}
        r = requests.get(url, headers=HEADERS, params=params, timeout=10)
        if r.status_code != 200:
            continue
        df = pd.DataFrame(r.json().get("positions", []))
        if not df.empty:
            df["platform"] = proto
            dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_prices(addresses: list[str]) -> dict[str, float]:
    body = {"addresses": addresses, "chain_id": CHAIN_ID}
    r = requests.post(f"{API_BASE}/token-info", json=body, headers=HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json().get("data", [])
    return {item["address"].lower(): float(item.get("price_usd") or 0) for item in data}

# ─── Data retrieval ─────────────────────────────────────────────────────────────
pos = fetch_lending_positions(wallet)
if pos.empty:
    st.error("No lending positions found for this wallet.")
    st.stop()

# ─── Dynamic column detection ───────────────────────────────────────────────────
def find_col(cols, *keywords):
    for c in cols:
        if all(kw.lower() in c.lower() for kw in keywords):
            return c
    return None

token_col   = find_col(pos.columns, "token", "address")
coll_col    = find_col(pos.columns, "collateral", "balance")
borrow_col  = find_col(pos.columns, "borrowed", "balance")
dec_col     = find_col(pos.columns, "decimals")
thresh_col  = find_col(pos.columns, "liquidation", "threshold")

required = {
    "token_address": token_col,
    "collateral_balance": coll_col,
    "borrowed_balance": borrow_col,
    "decimals": dec_col,
    "liquidation_threshold": thresh_col
}
missing = [name for name, col in required.items() if col is None]
if missing:
    st.error(f"Could not find columns: {missing}")
    st.stop()

# ─── Price fetching ─────────────────────────────────────────────────────────────
addrs = pos[token_col].str.lower().unique().tolist()
prices = fetch_prices(addrs)

# ─── Compute USD metrics ────────────────────────────────────────────────────────
pos["decimals"]       = pos[dec_col].astype(int)
pos["collateral_amt"] = pos[coll_col].astype(float) / (10 ** pos["decimals"])
pos["borrowed_amt"]   = pos[borrow_col].astype(float)   / (10 ** pos["decimals"])
pos["price_usd"]      = pos[token_col].str.lower().map(prices).fillna(0.0)
pos["collateral_usd"] = pos["collateral_amt"] * pos["price_usd"]
pos["borrowed_usd"]   = pos["borrowed_amt"]   * pos["price_usd"]

# ─── Aggregate per protocol ────────────────────────────────────────────────────
protocol_metrics = (
    pos.groupby("platform")
       .agg(total_collateral=("collateral_usd", "sum"),
            total_borrowed=("borrowed_usd",   "sum"))
)
protocol_metrics["coll_ratio"] = protocol_metrics["total_collateral"] / protocol_metrics["total_borrowed"]
protocol_metrics["health_factor"] = (
    protocol_metrics["coll_ratio"] /
    pos.groupby("platform")[thresh_col].first().astype(float)
)

# ─── Portfolio health factor ───────────────────────────────────────────────────
portfolio_hf = protocol_metrics["health_factor"].min()

# ─── Track history ─────────────────────────────────────────────────────────────
now = datetime.now(timezone.utc)
if "history" not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=["timestamp", "portfolio_hf"])
hist = st.session_state.history
new = pd.DataFrame([{"timestamp": now, "portfolio_hf": portfolio_hf}])
hist = pd.concat([hist, new], ignore_index=True).drop_duplicates("timestamp")
st.session_state.history = hist

# ─── Display metrics ───────────────────────────────────────────────────────────
c1, c2 = st.columns(2)
c1.metric("Portfolio Health Factor", f"{portfolio_hf:.2f}")
c2.dataframe(protocol_metrics[["total_collateral","total_borrowed","health_factor"]]
             .style.format({"total_collateral":"${:,.2f}",
                            "total_borrowed":"${:,.2f}",
                            "health_factor":"{:.2f}"}),
             use_container_width=True)

st.subheader("Historical Portfolio Health Factor")
st.line_chart(st.session_state.history.set_index("timestamp")["portfolio_hf"])

st.subheader("Position Breakdown")
pos.rename(columns={
    token_col: "token_address",
    coll_col: "collateral_balance",
    borrow_col: "borrowed_balance",
    dec_col: "decimals",
    thresh_col: "liquidation_threshold"
})[[
    "platform", "token_address", "collateral_amt", "borrowed_amt",
    "price_usd", "collateral_usd", "borrowed_usd", "liquidation_threshold"
]]
