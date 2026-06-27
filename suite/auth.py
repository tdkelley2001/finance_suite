from __future__ import annotations

from typing import Any

import streamlit as st

from suite.state import STATE_KEY
from suite.supabase_client import (
    SupabaseConfigError,
    clear_supabase_client,
    get_supabase,
)


SESSION_KEY = "supabase_session"
USER_KEY = "supabase_user"
PROFILE_LOADED_KEY = "profile_loaded_for_user"


def render_auth_gate() -> Any:
    """Render login/signup UI and stop the app until a user is authenticated."""
    if is_authenticated():
        return st.session_state[SESSION_KEY]

    st.title("Money Lab")
    st.caption("Sign in to save and restore your financial profile.")

    try:
        supabase = get_supabase()
    except SupabaseConfigError as exc:
        st.error(str(exc))
        st.stop()

    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Email", key="login_email").strip()
            password = st.text_input(
                "Password",
                type="password",
                key="login_password",
            )
            submitted = st.form_submit_button("Log in", use_container_width=True)

        if submitted:
            if not email or not password:
                st.error("Enter your email and password.")
            else:
                try:
                    response = supabase.auth.sign_in_with_password(
                        {"email": email, "password": password}
                    )
                except Exception as exc:  # Supabase auth errors are client-library exceptions.
                    st.error(f"Could not log in: {exc}")
                else:
                    if _store_auth_response(response):
                        st.rerun()

    with tab_signup:
        with st.form("signup_form", clear_on_submit=False):
            email = st.text_input("Email", key="signup_email").strip()
            password = st.text_input(
                "Password",
                type="password",
                key="signup_password",
            )
            submitted = st.form_submit_button(
                "Create account",
                use_container_width=True,
            )

        if submitted:
            if not email or not password:
                st.error("Enter an email and password.")
            else:
                try:
                    response = supabase.auth.sign_up(
                        {"email": email, "password": password}
                    )
                except Exception as exc:
                    st.error(f"Could not create account: {exc}")
                else:
                    if getattr(response, "session", None):
                        if _store_auth_response(response):
                            st.rerun()
                    st.success(
                        "Account created. Check your email to confirm your account, "
                        "then log in."
                    )

    st.stop()


def render_account_controls() -> None:
    user = get_current_user()
    if user is None:
        return

    with st.sidebar.expander("Account", expanded=False):
        st.caption(getattr(user, "email", "") or getattr(user, "id", "Signed in"))
        if st.button("Log out", use_container_width=True):
            logout()


def is_authenticated() -> bool:
    return SESSION_KEY in st.session_state and USER_KEY in st.session_state


def get_current_user() -> Any | None:
    return st.session_state.get(USER_KEY)


def logout() -> None:
    try:
        get_supabase().auth.sign_out()
    except Exception:
        pass

    for key in (
        SESSION_KEY,
        USER_KEY,
        PROFILE_LOADED_KEY,
        STATE_KEY,
    ):
        st.session_state.pop(key, None)
    clear_supabase_client()
    st.rerun()


def _store_auth_response(response: Any) -> bool:
    session = getattr(response, "session", None)
    user = getattr(response, "user", None)
    if session is None or user is None:
        st.error("Authentication did not return a user session.")
        return False

    st.session_state[SESSION_KEY] = session
    st.session_state[USER_KEY] = user
    return True
