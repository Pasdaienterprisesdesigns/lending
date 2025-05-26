import streamlit as st
import pandas as pd
import plotly.express as px
import requests

# ─── CONFIG ─────────────────────────────────────────────────────────────────────
st.set_page_config("📊 Multichain Wallet Dashboard", layout="wide")
st.title("📊 Multichain Wallet Dashboard")

# 🔐 HARD-CODED API KEY (⚠️ only for local/dev use)
X_SIM_API_KEY = "sim_444cGnNxG0exoklzAjwNsmIGcv03PBDG"
BASE_URL = "https://api.sim.dune.com/v1"

# ─── API CALL ───────────────────────────────────────────────────────────────────
def get_wallet_balances(address):
    url = f"{BASE_URL}/evm/balances/{address}"
    headers = {"X-Sim-Api-Key": X_SIM_API_KEY}
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        return None, res.text
    return res.json(), None

# ─── DATA PROCESSING ────────────────────────────────────────────────────────────
def process_balances(data):
    tokens = data.get("data", [])
    df = pd.DataFrame(tokens)
    if df.empty:
        return df
    df["usd_value"] = df["amount"].astype(float) * df["price_usd"].astype(float)
    df = df[df["usd_value"] > 0]
    return df

def filter_by_min_value(df, threshold=1):
    return df[df["usd_value"] >= threshold]

def summarize_portfolio(df):
    total = df["usd_value"].sum()
    by_chain = df.groupby("chain")["usd_value"].sum().reset_index()
    return total, by_chain

# ─── UI INPUT ────────────────────────────────────────────────────────────────────
wallet_address = st.text_input("Enter a wallet address:", value="0xd8da6bf26964af9d7eed9e03e53415d37aa96045")

if st.button("Fetch Data") or wallet_address:
    with st.spinner("Fetching balances..."):
        data, error = get_wallet_balances(wallet_address)

    if error:
        st.error(f"Error: {error}")
    else:
        df = process_balances(data)
        if df.empty:
            st.warning("No tokens found.")
        else:
            show_dust = st.checkbox("Show tokens under $1?", value=False)
            df_filtered = df if show_dust else filter_by_min_value(df)

            # Total summary
            total_usd, per_chain = summarize_portfolio(df_filtered)
            st.subheader(f"💰 Total Portfolio Value: ${total_usd:,.2f}")

            # Charts
            col1, col2 = st.columns(2)
            with col1:
                pie = px.pie(df_filtered, names="symbol", values="usd_value", title="Token Distribution")
                st.plotly_chart(pie, use_container_width=True)
            with col2:
                bar = px.bar(per_chain, x="chain", y="usd_value", title="Value by Chain")
                st.plotly_chart(bar, use_container_width=True)

            # Table
            st.markdown("### 📄 Token Holdings")
            st.dataframe(df_filtered.sort_values("usd_value", ascending=False)[[
                "symbol", "amount", "price_usd", "usd_value", "chain"
            ]])

            # Download button
            st.download_button(
                label="📥 Download as CSV",
                data=df_filtered.to_csv(index=False),
                file_name=f"{wallet_address}_balances.csv",
                mime="text/csv"
            )
