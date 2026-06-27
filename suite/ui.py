from __future__ import annotations

import math
from dataclasses import asdict, is_dataclass
from importlib import resources
from typing import Any

import streamlit as st

from suite.tools import SuiteTool


APP_TITLE = "Money Lab"
APP_CAPTION = (
    "Transparent financial models for exploring tradeoffs, risk, and assumptions."
)

EDUCATIONAL_WARNING = (
    "This tool is for educational and exploratory purposes only. It is not "
    "financial advice or a recommendation. Results are assumption-dependent "
    "and represent hypothetical outcomes, not predictions."
)


def configure_page() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")


def render_suite_header() -> None:
    st.title(APP_TITLE)
    st.caption(APP_CAPTION)


def select_tool(tools: list[SuiteTool]) -> SuiteTool:
    labels = [tool.nav_label for tool in tools]
    selected_label = st.sidebar.selectbox("Select a tool", labels)
    return tools[labels.index(selected_label)]


def render_tool_header(
    tool_or_title: SuiteTool | str,
    caption: str = "",
    *,
    icon: str = "",
    advice_warning: bool = False,
) -> None:
    if isinstance(tool_or_title, SuiteTool):
        title = tool_or_title.title
        caption = tool_or_title.caption
        icon = tool_or_title.icon
        advice_warning = tool_or_title.advice_warning
    else:
        title = tool_or_title

    heading = f"{icon} {title}" if icon else title
    st.header(heading)
    if caption:
        st.caption(caption)
    if advice_warning:
        st.warning(EDUCATIONAL_WARNING)


def money(value: float, digits: int = 0) -> str:
    return f"${value:,.{digits}f}"


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default

    if math.isnan(numeric):
        return default
    return numeric


def flatten_assumptions(sections: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for section, params in sections.items():
        if is_dataclass(params):
            params = asdict(params)

        if isinstance(params, dict):
            for key, value in params.items():
                rows.append(
                    {
                        "Category": section.title(),
                        "Parameter": key.replace("_", " ").title(),
                        "Value": value,
                    }
                )
        else:
            rows.append(
                {
                    "Category": "Mode",
                    "Parameter": section,
                    "Value": params,
                }
            )

    return rows


def read_package_text(package_name: str, relative_path: str) -> str:
    return (
        resources.files(package_name)
        .joinpath(relative_path)
        .read_text(encoding="utf-8")
    )
