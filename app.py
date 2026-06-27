import streamlit as st

from suite.auth import render_account_controls, render_auth_gate
from suite.profile_storage import (
    ensure_profile_loaded,
    save_profile,
)
from suite.registry import TOOLS
from suite.state import render_state_sources
from suite.ui import configure_page, render_suite_header, select_tool


def main() -> None:
    configure_page()
    render_auth_gate()
    try:
        ensure_profile_loaded()
    except Exception as exc:
        st.sidebar.error(f"Could not load saved profile: {exc}")

    render_suite_header()
    render_account_controls()

    tool = select_tool(TOOLS)
    tool.render(tool)
    try:
        save_profile()
    except Exception as exc:
        st.sidebar.error(f"Could not save profile: {exc}")
    render_state_sources()


if __name__ == "__main__":
    main()
