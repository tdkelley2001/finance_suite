from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
OAUTH_STATE_MAX_AGE_SECONDS = 15 * 60


def render_auth_gate() -> Any:
    """Render login/signup UI and stop the app until a user is authenticated."""
    try:
        supabase = get_supabase()
    except SupabaseConfigError as exc:
        st.title("Money Lab")
        st.error(str(exc))
        st.stop()

    _handle_oauth_callback(supabase)

    if is_authenticated():
        return st.session_state[SESSION_KEY]

    st.title("Money Lab")
    st.caption("Sign in to save and restore your financial profile.")

    _render_google_login(supabase)
    st.divider()

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


def _handle_oauth_callback(supabase: Any) -> None:
    error = _get_query_param("error_description") or _get_query_param("error")
    if error:
        st.error(f"Could not log in with Google: {error}")
        _clear_auth_query_params()
        st.stop()

    code = _get_query_param("code")
    if not code or is_authenticated():
        return

    try:
        code_verifier = _oauth_code_verifier_from_state(_get_query_param("state"))
        exchange_params = {
            "auth_code": code,
            "redirect_to": _oauth_redirect_url(),
        }
        if code_verifier:
            exchange_params["code_verifier"] = code_verifier

        response = supabase.auth.exchange_code_for_session(
            exchange_params
        )
    except Exception as exc:
        _clear_auth_query_params()
        st.error(f"Could not complete Google login: {exc}")
        st.stop()

    if _store_auth_response(response):
        _clear_auth_query_params()
        st.rerun()


def _render_google_login(supabase: Any) -> None:
    try:
        response = supabase.auth.sign_in_with_oauth(
            {
                "provider": "google",
                "options": {
                    "redirect_to": _oauth_redirect_url(),
                    "query_params": {
                        "access_type": "offline",
                        "prompt": "consent",
                    },
                },
            }
        )
    except Exception as exc:
        st.error(f"Could not start Google login: {exc}")
        return

    url = _oauth_url_with_state(supabase, getattr(response, "url", ""))
    st.link_button(
        "Continue with Google",
        url,
        use_container_width=True,
    )


def _oauth_redirect_url() -> str:
    configured_url = _configured_redirect_url()
    if configured_url:
        return configured_url

    current_url = str(getattr(st.context, "url", "") or "")
    if not current_url:
        return ""

    parts = urlsplit(current_url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _configured_redirect_url() -> str:
    try:
        return str(st.secrets["app"]["redirect_url"]).strip()
    except (KeyError, TypeError):
        return ""


def _get_query_param(name: str) -> str:
    value = st.query_params.get(name, "")
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value)


def _clear_auth_query_params() -> None:
    for key in ("code", "error", "error_description", "state"):
        if key in st.query_params:
            del st.query_params[key]


def _oauth_url_with_state(supabase: Any, url: str) -> str:
    code_verifier = _stored_code_verifier(supabase)
    if not code_verifier:
        return url

    state = _sign_oauth_state(
        {
            "code_verifier": code_verifier,
            "iat": int(time.time()),
        }
    )
    return _replace_query_param(url, "state", state)


def _stored_code_verifier(supabase: Any) -> str:
    auth = getattr(supabase, "auth", None)
    storage = getattr(auth, "_storage", None)
    storage_key = getattr(auth, "_storage_key", "")
    if storage is None or not storage_key:
        return ""

    try:
        return str(storage.get_item(f"{storage_key}-code-verifier") or "")
    except Exception:
        return ""


def _sign_oauth_state(payload: dict[str, Any]) -> str:
    raw_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    encoded_payload = _base64_url_encode(raw_payload)
    signature = hmac.new(
        _oauth_state_secret().encode(),
        encoded_payload.encode(),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_base64_url_encode(signature)}"


def _oauth_code_verifier_from_state(state: str) -> str:
    if not state:
        return ""

    try:
        encoded_payload, encoded_signature = state.split(".", 1)
    except ValueError:
        return ""

    expected_signature = hmac.new(
        _oauth_state_secret().encode(),
        encoded_payload.encode(),
        hashlib.sha256,
    ).digest()
    supplied_signature = _base64_url_decode(encoded_signature)
    if not hmac.compare_digest(expected_signature, supplied_signature):
        return ""

    try:
        payload = json.loads(_base64_url_decode(encoded_payload))
    except (json.JSONDecodeError, ValueError):
        return ""

    issued_at = int(payload.get("iat") or 0)
    if issued_at <= 0 or time.time() - issued_at > OAUTH_STATE_MAX_AGE_SECONDS:
        return ""

    return str(payload.get("code_verifier") or "")


def _oauth_state_secret() -> str:
    try:
        secret = str(st.secrets["app"]["oauth_state_secret"]).strip()
        if secret:
            return secret
    except (KeyError, TypeError):
        pass

    return str(st.secrets["supabase"]["anon_key"])


def _base64_url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _base64_url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _replace_query_param(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params[key] = value
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(params),
            parts.fragment,
        )
    )
