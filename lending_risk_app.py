import streamlit as st
import pandas as pd
import requests
import plotly.express as px

st.set_page_config("🧾 Token Holder Explorer", layout="wide")
st.title("🧾 Token Holder Explorer")

X_SIM_API_KEY = "sim_444cGnNxG0exoklzAjwNsmIGcv03PBDG"
BASE_URL = "https://api.sim.dune.com/v1"

def get_token_holders(token_address):
    url = f"{BASE_URL}/evm/token_holders/{token_address}"
    headers = {"X-Sim-Api-Key": X_SIM_API_KEY}
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        return None, res.text
    return res.json().get("data", []), None

def process_holder_data(data):
    df = pd.DataFrame(data)
    if df.empty:
        return df
    df["balance"] = df["balance"].astype(float)
    df["pct_supply"] = df["percent_supply"].astype(float)
    df["etherscan"] = df["holder"].apply(lambda x: f"https://etherscan.io/address/{x}")
    return df

token_address = st.text_input("Enter token contract address (EVM):")

if st.button("Fetch Holders") and token_address:
    with st.spinner("Fetching holders..."):
        data, error = get_token_holders(token_address)

    if error:
        st.error(f"Error: {error}")
    elif not data:
        st.warning("No holder data found.")
    else:
        df = process_holder_data(data)

        search_addr = st.text_input("Search for wallet address:")
        if search_addr:
            df = df[df["holder"].str.contains(search_addr, case=False)]

        top_10 = df.head(10)
        rest = df.iloc[10:]
        pie_df = pd.DataFrame({
            "Category": ["Top 10", "Rest"],
            "Percentage of Supply": [top_10["pct_supply"].sum(), rest["pct_supply"].sum()]
        })

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Top Holders")
            st.dataframe(df[["holder", "balance", "pct_supply", "etherscan"]].rename(columns={
                "holder": "Wallet",
                "balance": "Token Balance",
                "pct_supply": "% Supply",
                "etherscan": "Etherscan"
            }))

        with col2:
            st.subheader("Top 10 vs Rest")
            pie = px.pie(pie_df, names="Category", values="Percentage of Supply")
            st.plotly_chart(pie, use_container_width=True)
