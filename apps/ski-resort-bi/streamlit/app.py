"""Streamlit entry point — gold KPI dashboard + embedded Cortex Code chat (REQ-014).

Run:
    SNOWFLAKE_CONNECTION_NAME=myconnection \\
        python3 -m streamlit run /Users/jdemlow/00_Code/github/AgentMangement/streamlit/app.py
"""

from __future__ import annotations

import os

import streamlit as st

import _bootstrap

_bootstrap.install()

from chat_panel import render_chat_panel
from dashboard import render_dashboard, reset_connection_cache


def _connection_picker() -> str:
    default = os.getenv("SNOWFLAKE_CONNECTION_NAME") or "myconnection"
    with st.sidebar:
        st.header("Connection")
        connection = st.text_input("Snowflake connection name", value=default, key="coco_conn")
        st.caption(
            "Resolved from `~/.snowflake/connections.toml`. "
            "The Cortex Code Agent SDK uses this same connection."
        )
        if st.button("Reset Snowflake connection", use_container_width=True):
            reset_connection_cache()
            st.session_state.pop("bi_last_answer", None)
            st.session_state.pop("bi_trace", None)
            st.toast("Snowflake connection cache reset.")
            st.rerun()
    return connection


def main() -> None:
    st.set_page_config(layout="wide", page_title="Ski KPIs · Cortex Code chat")
    connection = _connection_picker()

    tcol, bcol = st.columns([4, 1], vertical_alignment="bottom")
    with tcol:
        st.title("Ski Resort — Gold KPIs")
    with bcol:
        st.caption("AI BI panel below")

    render_dashboard(suppress_title=True, connection_name=connection)
    st.divider()
    st.subheader("Ask about this dashboard")
    render_chat_panel(connection)


if __name__ == "__main__":
    main()
