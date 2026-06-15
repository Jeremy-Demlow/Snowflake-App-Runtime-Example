"""
App Template (Streamlit in Snowflake) — copy me to apps/<your-app>/.

Reads the single shared, read-only data database SKI_RESORT_DEMO. Replace the
body with your own dashboard. See apps/streamlit-dashboard/ for a full example.
"""
import streamlit as st

st.set_page_config(page_title="My App", page_icon="🟦", layout="wide")

# In Snowflake the app uses its embedded identity; locally it resolves from
# SNOWFLAKE_DEFAULT_CONNECTION_NAME. The name is positional — do not pass
# connection_name=.
conn = st.connection("snowflake")

DEMO_DB = "SKI_RESORT_DEMO"  # one shared read-only data copy for every env

st.title("My App")
st.caption("Starter template — reading from SKI_RESORT_DEMO (read-only).")

df = conn.query(
    f"SELECT COUNT(*) AS total_pass_scans FROM {DEMO_DB}.MARTS.FACT_PASS_USAGE",
    ttl=600,
)
st.metric("Pass scans in dataset", f"{int(df.iloc[0]['TOTAL_PASS_SCANS']):,}")
