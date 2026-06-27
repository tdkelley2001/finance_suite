from __future__ import annotations

import streamlit as st
from supabase import Client, create_client


CLIENT_KEY = "supabase_client"


class SupabaseConfigError(RuntimeError):
    """Raised when Supabase secrets are missing or incomplete."""


def _get_secret(name: str) -> str:
    try:
        value = st.secrets["supabase"][name]
    except (KeyError, TypeError):
        raise SupabaseConfigError(
            "Supabase is not configured. Add supabase.url and "
            "supabase.anon_key to .streamlit/secrets.toml."
        ) from None

    value = str(value).strip()
    if not value:
        raise SupabaseConfigError(
            "Supabase is not configured. Add non-empty supabase.url and "
            "supabase.anon_key values to .streamlit/secrets.toml."
        )
    return value


def get_supabase() -> Client:
    if CLIENT_KEY not in st.session_state:
        st.session_state[CLIENT_KEY] = create_client(
            _get_secret("url"),
            _get_secret("anon_key"),
        )
    return st.session_state[CLIENT_KEY]


def clear_supabase_client() -> None:
    st.session_state.pop(CLIENT_KEY, None)
