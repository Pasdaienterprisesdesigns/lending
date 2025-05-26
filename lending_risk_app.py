import streamlit as st
import requests

st.set_page_config("🔍 Token Metadata Explorer", layout="wide")
st.title("🔍 Token Metadata Explorer")

X_SIM_API_KEY = "sim_444cGnNxG0exoklzAjwNsmIGcv03PBDG"
BASE_URL = "https://api.sim.dune.com/v1"

def get_token_metadata(token_address):
    url = f"{BASE_URL}/evm/token_metadata/{token_address}"
    headers = {"X-Sim-Api-Key": X_SIM_API_KEY}
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        return None, res.text
    return res.json().get("data", {}), None

token_address = st.text_input("Enter Token Contract Address (EVM):")

if st.button("Fetch Metadata") and token_address:
    with st.spinner("Fetching token metadata..."):
        data, error = get_token_metadata(token_address)

    if error:
        st.error(f"Error: {error}")
    elif not data:
        st.warning("No metadata found.")
    else:
        col1, col2 = st.columns([1, 2])
        with col1:
            if data.get("image"):
                st.image(data["image"], width=150)

        with col2:
            st.subheader(f"{data.get('name', 'Unknown Token')} ({data.get('symbol', 'N/A')})")
            st.markdown(f"""
            **Symbol:** {data.get('symbol', 'N/A')}  
            **Decimals:** {data.get('decimals', 'N/A')}  
            **Total Supply:** {data.get('total_supply', 'N/A')}  

            **Etherscan:** [View Token](https://etherscan.io/token/{token_address})
            """)

            st.markdown(f"""
            **Additional Research:**  
            - [CoinGecko](https://www.coingecko.com/en/search?query={data.get('symbol', '')})
            - [CoinMarketCap](https://coinmarketcap.com/currencies/{data.get('symbol', '').lower()})
            - [DEX Screener](https://dexscreener.com/ethereum/{token_address})
            """)

