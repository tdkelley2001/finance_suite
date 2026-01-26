import streamlit as st
from collections import defaultdict

from config.param_meta import PARAM_META
from ui.assumptions_view import values_equal, format_assumption_value


def collect_assumptions(baseline, *, context_key: str) -> tuple[dict, list[dict], int]:
    overrides = {}
    assumption_rows = []

    # group params dynamically
    grouped = defaultdict(list)
    for param, meta in PARAM_META.items():
        grouped[meta["group"]].append(param)

    # --------------------------------------------------
    # Model Regime rows (prepend)
    # --------------------------------------------------
    for group_name, params in grouped.items():
        with st.expander(group_name, expanded=False):
            for param in params:
                meta = PARAM_META[param]
                kind = meta["kind"]
                label = meta["label"]
                help_text = meta.get("help")

                base_val = getattr(baseline, param)
                # --- Render widget with BASELINE value ---
                if kind == "percent":
                    ui_val = st.number_input(
                        label,
                        value=float(base_val) * 100,
                        step=0.1,
                        format="%.2f",
                        help=help_text,
                        key=f"{context_key}_{param}",
                    ) / 100

                elif kind == "currency":
                    ui_val = st.number_input(
                        label,
                        value=float(base_val),
                        step=100.0,
                        format="%.0f",
                        help=help_text,
                        key=f"{context_key}_{param}",
                    )

                elif kind == "int":
                    ui_val = st.number_input(
                        label,
                        value=int(base_val),
                        step=1,
                        help=help_text,
                        key=f"{context_key}_{param}",
                    )

                else:
                    raise ValueError(f"Unsupported parameter type: {kind}")

                # --- Override detection (stateless, safe) ---
                is_override = not values_equal(ui_val, base_val)

                if is_override:
                    overrides[param] = ui_val
                    st.caption("✏️ Overridden from scenario baseline")

                assumption_rows.append(
                    {
                        "Group": meta["group"],
                        "Parameter": label,
                        "Baseline": format_assumption_value(base_val, kind),
                        "Value": format_assumption_value(ui_val, kind),
                        "Overridden": is_override,
                    }
                )

    overrides = overrides or {}

    return overrides, assumption_rows, len(overrides)