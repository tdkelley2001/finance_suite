from __future__ import annotations

from typing import Any

import streamlit as st

from suite.auth import (
    PROFILE_LOADED_KEY,
    get_current_user,
    is_dev_auth_bypass_active,
)
from suite.state import (
    hydrate_widgets_from_state,
    set_user_state,
    state_from_dict,
    state_to_dict,
)
from suite.supabase_client import get_supabase


PROFILE_TABLE = "user_profiles"
SCHEMA_VERSION = 1


def ensure_profile_loaded() -> bool:
    """Load the signed-in user's saved profile exactly once per session."""
    if is_dev_auth_bypass_active():
        return False

    user = get_current_user()
    if user is None:
        return False

    user_id = str(user.id)
    if st.session_state.get(PROFILE_LOADED_KEY) == user_id:
        return True

    loaded = load_profile()
    st.session_state[PROFILE_LOADED_KEY] = user_id
    return loaded


def load_profile() -> bool:
    if is_dev_auth_bypass_active():
        return False

    user = _require_user()
    response = (
        get_supabase()
        .table(PROFILE_TABLE)
        .select("state_json")
        .eq("user_id", str(user.id))
        .limit(1)
        .execute()
    )

    rows = response.data or []
    if not rows:
        return False

    state_json = rows[0].get("state_json")
    if not isinstance(state_json, dict):
        raise ValueError("Saved profile is missing state_json.")

    saved_state = state_from_dict(state_json)
    set_user_state(saved_state)
    hydrate_widgets_from_state(saved_state)
    return True


def save_profile() -> Any:
    if is_dev_auth_bypass_active():
        return None

    user = _require_user()
    state_dict = state_to_dict()

    return (
        get_supabase()
        .table(PROFILE_TABLE)
        .upsert(
            {
                "user_id": str(user.id),
                "email": getattr(user, "email", ""),
                "state_json": state_dict,
                "schema_version": SCHEMA_VERSION,
            },
            on_conflict="user_id",
        )
        .execute()
    )


def _require_user() -> Any:
    user = get_current_user()
    if user is None:
        raise RuntimeError("No authenticated user is available.")
    return user
