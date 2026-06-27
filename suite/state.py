from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st


STATE_KEY = "money_lab_state"
DEFAULT_SCENARIO = "Current"

DEFAULT_GLOBAL_ASSUMPTIONS = {
    "inflation": 0.025,
    "expected_portfolio_return": 0.07,
    "expected_portfolio_volatility": 0.15,
    "cash_return": 0.04,
    "mortgage_rate": 0.065,
    "property_tax_rate": 0.012,
    "homeowners_insurance_annual": 1500.0,
    "pmi_rate": 0.01,
    "home_appreciation": 0.03,
    "rent_growth": 0.03,
    "default_tax_rate": 0.22,
    "capital_gains_tax_rate": 0.15,
    "default_withdrawal_rate": 0.04,
    "planning_horizon_years": 30,
    "recommended_emergency_months": 6,
}


@dataclass
class DataProvenance:
    source_type: str = "manual"
    source_id: str = ""
    label: str = ""
    updated_at: str = ""


@dataclass
class MonthlyCashFlowState:
    net_monthly_income: float = 0.0
    required_monthly_expenses: float = 0.0
    discretionary_monthly_expenses: float = 0.0
    planned_monthly_savings: float = 0.0
    savings_rate: float = 0.0
    emergency_expense_baseline: float = 0.0
    min_monthly_buffer: float = 500.0
    source: str = ""
    provenance: dict[str, DataProvenance] = field(default_factory=dict)

    @property
    def non_housing_expenses(self) -> float:
        return self.required_monthly_expenses + self.discretionary_monthly_expenses


@dataclass
class FinancialAccount:
    name: str
    account_type: str
    balance: float = 0.0
    tax_treatment: str = ""
    provenance: dict[str, DataProvenance] = field(default_factory=dict)


@dataclass
class Asset:
    name: str
    asset_type: str
    value: float = 0.0
    provenance: dict[str, DataProvenance] = field(default_factory=dict)


@dataclass
class Liability:
    name: str
    liability_type: str
    balance: float = 0.0
    payment: float = 0.0
    interest_rate: float = 0.0
    provenance: dict[str, DataProvenance] = field(default_factory=dict)


@dataclass
class BalanceSheetState:
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    net_worth: float = 0.0
    liquid_assets: float = 0.0
    retirement_assets: float = 0.0
    taxable_assets: float = 0.0
    provenance: dict[str, DataProvenance] = field(default_factory=dict)


@dataclass
class FinancialGoal:
    name: str
    goal_type: str
    target_amount: float = 0.0
    target_date: str = ""
    priority: str = ""
    provenance: dict[str, DataProvenance] = field(default_factory=dict)


@dataclass
class ProfileState:
    monthly_cash_flow: MonthlyCashFlowState = field(default_factory=MonthlyCashFlowState)
    accounts: list[FinancialAccount] = field(default_factory=list)
    balance_sheet: BalanceSheetState = field(default_factory=BalanceSheetState)
    assets: list[Asset] = field(default_factory=list)
    liabilities: list[Liability] = field(default_factory=list)
    goals: list[FinancialGoal] = field(default_factory=list)


@dataclass
class AssumptionsState:
    global_defaults: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_GLOBAL_ASSUMPTIONS)
    )
    provenance: dict[str, DataProvenance] = field(default_factory=dict)


@dataclass
class Scenario:
    name: str = DEFAULT_SCENARIO
    description: str = ""
    assumptions_overrides: dict[str, Any] = field(default_factory=dict)
    tool_inputs: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, DataProvenance] = field(default_factory=dict)


@dataclass
class ScenariosState:
    active: str = DEFAULT_SCENARIO
    items: dict[str, Scenario] = field(
        default_factory=lambda: {DEFAULT_SCENARIO: Scenario()}
    )


@dataclass
class ToolOutputsState:
    outputs: dict[str, Any] = field(default_factory=dict)


@dataclass
class UserState:
    updated_at: str = ""
    profile: ProfileState = field(default_factory=ProfileState)
    assumptions: AssumptionsState = field(default_factory=AssumptionsState)
    scenarios: ScenariosState = field(default_factory=ScenariosState)
    tool_outputs: ToolOutputsState = field(default_factory=ToolOutputsState)

    @property
    def cash_flow(self) -> MonthlyCashFlowState:
        return self.profile.monthly_cash_flow


SharedCashFlowState = MonthlyCashFlowState


def default_user_state() -> UserState:
    state = UserState(updated_at=_timestamp())
    _ensure_default_assumptions(state)
    return state


def get_user_state() -> UserState:
    if STATE_KEY not in st.session_state:
        st.session_state[STATE_KEY] = default_user_state()
    elif not isinstance(st.session_state[STATE_KEY], UserState):
        st.session_state[STATE_KEY] = _coerce_state(st.session_state[STATE_KEY])
    return st.session_state[STATE_KEY]


def set_user_state(state: UserState) -> None:
    ensure_active_scenario(state)
    _ensure_default_assumptions(state)
    state.updated_at = _timestamp()
    st.session_state[STATE_KEY] = state


def ensure_active_scenario(state: UserState) -> Scenario:
    if state.scenarios.active not in state.scenarios.items:
        state.scenarios.items[state.scenarios.active] = Scenario(
            name=state.scenarios.active
        )
    return state.scenarios.items[state.scenarios.active]


def provenance(source_id: str, label: str = "", source_type: str = "tool") -> DataProvenance:
    return DataProvenance(
        source_type=source_type,
        source_id=source_id,
        label=label,
        updated_at=_timestamp(),
    )


def update_cash_flow(cash_flow: SharedCashFlowState, source_id: str = "") -> None:
    state = get_user_state()
    source = source_id or cash_flow.source or "manual"
    cash_flow.provenance = {
        "net_monthly_income": provenance(source, "Net monthly income"),
        "required_monthly_expenses": provenance(source, "Required monthly expenses"),
        "discretionary_monthly_expenses": provenance(source, "Discretionary monthly expenses"),
        "planned_monthly_savings": provenance(source, "Planned monthly savings"),
        "savings_rate": provenance(source, "Savings rate"),
        "emergency_expense_baseline": provenance(source, "Emergency expense baseline"),
        "min_monthly_buffer": provenance(source, "Minimum monthly buffer"),
    }
    state.profile.monthly_cash_flow = cash_flow
    set_user_state(state)


def update_net_worth_profile(
    *,
    accounts: list[FinancialAccount],
    assets: list[Asset],
    liabilities: list[Liability],
    balance_sheet: BalanceSheetState,
    source_id: str = "net_worth",
) -> None:
    state = get_user_state()
    source_fields = {
        "accounts": "Accounts",
        "assets": "Assets",
        "liabilities": "Liabilities",
        "total_assets": "Total assets",
        "total_liabilities": "Total liabilities",
        "net_worth": "Net worth",
        "liquid_assets": "Liquid assets",
        "retirement_assets": "Retirement assets",
        "taxable_assets": "Taxable assets",
    }
    balance_sheet.provenance = {
        key: provenance(source_id, label)
        for key, label in source_fields.items()
        if key not in {"accounts", "assets", "liabilities"}
    }

    item_provenance = {"value": provenance(source_id, "Net worth tracker")}
    for account in accounts:
        account.provenance = dict(item_provenance)
    for asset in assets:
        asset.provenance = dict(item_provenance)
    for liability in liabilities:
        liability.provenance = {
            "balance": provenance(source_id, "Net worth tracker")
        }

    state.profile.accounts = accounts
    state.profile.assets = assets
    state.profile.liabilities = liabilities
    state.profile.balance_sheet = balance_sheet
    set_user_state(state)


def get_cash_flow() -> MonthlyCashFlowState:
    return get_user_state().profile.monthly_cash_flow


def get_assumption(key: str, default: Any = None) -> Any:
    state = get_user_state()
    return state.assumptions.global_defaults.get(key, default)


def update_assumption(
    key: str,
    value: Any,
    *,
    source_id: str = "manual",
    label: str = "",
    source_type: str = "manual",
) -> None:
    state = get_user_state()
    state.assumptions.global_defaults[key] = value
    state.assumptions.provenance[key] = provenance(
        source_id,
        label or key.replace("_", " ").title(),
        source_type=source_type,
    )
    set_user_state(state)


def get_tool_state(tool_key: str) -> dict[str, Any]:
    scenario = ensure_active_scenario(get_user_state())
    return dict(scenario.tool_inputs.get(tool_key, {}))


def update_tool_state(tool_key: str, values: dict[str, Any]) -> None:
    state = get_user_state()
    scenario = ensure_active_scenario(state)
    scenario.tool_inputs[tool_key] = {
        key: value for key, value in values.items() if value is not None
    }
    scenario.provenance[tool_key] = provenance(tool_key, "Tool inputs")
    set_user_state(state)


def update_tool_output(tool_key: str, summary: dict[str, Any]) -> None:
    state = get_user_state()
    state.tool_outputs.outputs[tool_key] = {
        "summary": summary,
        "provenance": asdict(provenance(tool_key, "Tool output")),
    }
    set_user_state(state)


def state_to_dict(state: UserState | None = None) -> dict[str, Any]:
    state = state or get_user_state()
    state.updated_at = _timestamp()
    return _json_safe(asdict(state))


def state_from_dict(data: dict[str, Any]) -> UserState:
    state = UserState(
        updated_at=str(data.get("updated_at") or _timestamp()),
        profile=_profile_from_dict(data.get("profile") or {}),
        assumptions=_assumptions_from_dict(data.get("assumptions") or {}),
        scenarios=_scenarios_from_dict(data.get("scenarios") or {}),
        tool_outputs=_tool_outputs_from_dict(data.get("tool_outputs") or {}),
    )
    _ensure_default_assumptions(state)
    return state


def dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return _json_safe(df.to_dict(orient="records"))


def _records_to_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(records)


def render_state_sources() -> None:
    cash_flow = get_cash_flow()
    if not cash_flow.provenance:
        return

    with st.sidebar.expander("Profile Sources", expanded=False):
        for field_name, source in cash_flow.provenance.items():
            label = source.label or field_name.replace("_", " ").title()
            source_label = source.source_id or source.source_type
            st.caption(f"{label}: {source_label}")


def hydrate_widgets_from_state(state: UserState) -> None:
    cash_flow = state.profile.monthly_cash_flow
    st.session_state["budget_net_monthly_income"] = cash_flow.net_monthly_income
    st.session_state["budget_planned_savings"] = cash_flow.planned_monthly_savings

    st.session_state["housing_net_monthly_income"] = cash_flow.net_monthly_income
    st.session_state["housing_non_housing_expenses"] = cash_flow.non_housing_expenses
    st.session_state["housing_planned_savings"] = cash_flow.planned_monthly_savings
    st.session_state["housing_min_monthly_buffer"] = cash_flow.min_monthly_buffer

    budget_state = _tool_state_from_state(state, "budget")
    expense_records = budget_state.get("expenses")
    if isinstance(expense_records, list):
        st.session_state["expenses_df"] = _records_to_dataframe(expense_records)

    housing_state = _tool_state_from_state(state, "housing_affordability")
    for key, value in housing_state.items():
        if value is not None:
            st.session_state[f"housing_{key}"] = value



def _tool_state_from_state(state: UserState, tool_key: str) -> dict[str, Any]:
    scenario = ensure_active_scenario(state)
    return dict(scenario.tool_inputs.get(tool_key, {}))


def _coerce_state(value: Any) -> UserState:
    if isinstance(value, dict):
        return state_from_dict(_json_safe(value))

    if hasattr(value, "profile"):
        return value

    return default_user_state()


def _profile_from_dict(data: dict[str, Any]) -> ProfileState:
    return ProfileState(
        monthly_cash_flow=MonthlyCashFlowState(
            **_known_fields(
                MonthlyCashFlowState,
                data.get("monthly_cash_flow") or {},
            )
        ),
        accounts=[
            FinancialAccount(**_known_fields(FinancialAccount, item))
            for item in data.get("accounts", [])
            if isinstance(item, dict)
        ],
        balance_sheet=BalanceSheetState(
            **_known_fields(
                BalanceSheetState,
                data.get("balance_sheet") or {},
            )
        ),
        assets=[
            Asset(**_known_fields(Asset, item))
            for item in data.get("assets", [])
            if isinstance(item, dict)
        ],
        liabilities=[
            Liability(**_known_fields(Liability, item))
            for item in data.get("liabilities", [])
            if isinstance(item, dict)
        ],
        goals=[
            FinancialGoal(**_known_fields(FinancialGoal, item))
            for item in data.get("goals", [])
            if isinstance(item, dict)
        ],
    )


def _assumptions_from_dict(data: dict[str, Any]) -> AssumptionsState:
    defaults = dict(DEFAULT_GLOBAL_ASSUMPTIONS)
    defaults.update(dict(data.get("global_defaults") or {}))
    return AssumptionsState(
        global_defaults=defaults,
        provenance=_provenance_map(data.get("provenance") or {}),
    )


def _ensure_default_assumptions(state: UserState) -> None:
    for key, value in DEFAULT_GLOBAL_ASSUMPTIONS.items():
        state.assumptions.global_defaults.setdefault(key, value)


def _scenarios_from_dict(data: dict[str, Any]) -> ScenariosState:
    items = {}
    for name, scenario_data in dict(data.get("items") or {}).items():
        if isinstance(scenario_data, dict):
            scenario = Scenario(**_known_fields(Scenario, scenario_data))
            scenario.provenance = _provenance_map(scenario_data.get("provenance") or {})
            items[name] = scenario

    if not items:
        items[DEFAULT_SCENARIO] = Scenario()

    active = str(data.get("active") or DEFAULT_SCENARIO)
    if active not in items:
        items[active] = Scenario(name=active)

    return ScenariosState(active=active, items=items)


def _tool_outputs_from_dict(data: dict[str, Any]) -> ToolOutputsState:
    return ToolOutputsState(outputs=dict(data.get("outputs") or {}))


def _provenance_map(values: dict[str, Any]) -> dict[str, DataProvenance]:
    return {
        key: DataProvenance(**_known_fields(DataProvenance, value))
        for key, value in values.items()
        if isinstance(value, dict)
    }


def _known_fields(model: type, values: dict[str, Any]) -> dict[str, Any]:
    field_names = set(getattr(model, "__dataclass_fields__", {}))
    cleaned = {}
    for key, value in values.items():
        if key not in field_names:
            continue
        if key == "provenance" and isinstance(value, dict):
            cleaned[key] = _provenance_map(value)
        else:
            cleaned[key] = value
    return cleaned


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
