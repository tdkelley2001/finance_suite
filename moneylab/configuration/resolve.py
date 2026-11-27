"""Resolve eligible inputs without modifying the baseline or any configuration layer."""

from dataclasses import fields, replace

from moneylab.domain.planning import ActivityKind, FinancialPlan
from moneylab.domain.profile import Account, Asset, FinancialProfile
from moneylab.domain.values import Source, SourceKind

from .models import (
    AnalysisOverrides,
    AnalysisRequest,
    AnalysisType,
    EconomicAssumptions,
    ModelPreferences,
    Preset,
    ResearchDefaults,
    Scenario,
)
from .snapshot import (
    InputOrigin, MissingAnalysisInput, ResolvedAnalysis, activity_amount_field,
    position_growth_field, position_valuation_field, validate_position_override,
)


def _select(section, record_type, layers, origins):
    values = {}
    for field in fields(record_type):
        for config, source in layers:
            value = getattr(getattr(config, section), field.name)
            if value is not None:
                values[field.name] = value
                origins.append(InputOrigin(f"{section}.{field.name}", source))
                break
    return record_type(**values)


def _validate_scenario(scenario, profile, plan, preset):
    for label, expected_id, record in (
        ("profile", scenario.profile_id, profile),
        ("plan", scenario.plan_id, plan),
        ("preset", scenario.preset_id, preset),
    ):
        if expected_id is not None and (record is None or record.revision.id != expected_id):
            raise ValueError(f"scenario requires {label} {expected_id}")


def _resolve_plan(plan, profile, subject, override_layers, origins):
    activities = {} if plan is None else {
        activity.id: activity for activity in plan.activities_for(profile, subject)
    }
    changes = {}
    for overrides, source in override_layers:
        for override in overrides.activity_amounts:
            activity = activities.get(override.activity_id)
            if activity is None or activity.kind is ActivityKind.DEBT_PAYMENT:
                raise ValueError(f"activity {override.activity_id} is ineligible for an amount override")
            override.amount.require_currency(activity.amount.currency)
            changes.setdefault(activity.id, (override.amount, source))
    if plan is None:
        return None

    plan_source = plan.source or Source(SourceKind.USER_PLAN, plan.revision)
    origins.append(InputOrigin("plan", plan_source))
    resolved = []
    for activity in plan.activities:
        amount, source = changes.get(activity.id, (activity.amount, activity.source or plan_source))
        origins.append(InputOrigin(activity_amount_field(activity.id), source))
        resolved.append(replace(activity, amount=amount) if activity.id in changes else activity)
    return replace(plan, activities=tuple(resolved))


def _resolve_positions(profile, inputs, override_layers, origins):
    positions = {position.id: position for position in profile.positions_for(inputs.subject)}
    selected = {}
    growth = {}
    for overrides, source in override_layers:
        for override in overrides.position_valuations:
            validate_position_override(override, positions, inputs.start_on)
            if override.position_id not in selected:
                selected[override.position_id] = override
                origins.append(InputOrigin(position_valuation_field(override.position_id), source))
        for entry in overrides.position_growth:
            if not isinstance(positions.get(entry.position_id), (Account, Asset)):
                raise ValueError(f"{entry.position_id} growth requires an in-scope account or asset")
            if entry.position_id not in growth:
                growth[entry.position_id] = entry
                origins.append(InputOrigin(position_growth_field(entry.position_id), source))
    return tuple(selected.values()), tuple(growth.values())


def resolve_analysis(
    request: AnalysisRequest,
    *,
    profile: FinancialProfile | None = None,
    plan: FinancialPlan | None = None,
    defaults: ResearchDefaults | None = None,
    preset: Preset | None = None,
    scenario: Scenario | None = None,
    local: AnalysisOverrides | None = None,
) -> ResolvedAnalysis:
    if not isinstance(request, AnalysisRequest):
        raise ValueError("expected an analysis request")
    origins = [InputOrigin("analysis.inputs", Source(SourceKind.USER_FACT))]
    context = (
        (profile, FinancialProfile), (plan, FinancialPlan), (defaults, ResearchDefaults),
        (preset, Preset), (scenario, Scenario), (local, AnalysisOverrides),
    )
    if request.analysis_type is AnalysisType.LOAN_PAYMENT:
        if any(record is not None for record, _ in context):
            raise ValueError("standalone loan analysis only accepts explicit loan inputs")
        return ResolvedAnalysis(request=request, origins=origins)

    for record, record_type in context:
        if record is not None and not isinstance(record, record_type):
            raise ValueError(f"expected {record_type.__name__}")
    if profile is None:
        raise MissingAnalysisInput("projection requires a financial profile")
    if scenario is not None:
        _validate_scenario(scenario, profile, plan, preset)

    override_layers = []
    if local is not None:
        override_layers.append((local, Source(SourceKind.LOCAL_OVERRIDE)))
    if scenario is not None:
        override_layers.append((scenario.overrides, Source(SourceKind.SCENARIO_OVERRIDE, scenario.revision)))
    config_layers = list(override_layers)
    if preset is not None:
        config_layers.append((preset, Source(SourceKind.PRESET, preset.revision)))
    if defaults is not None:
        config_layers.append((defaults, Source(SourceKind.RESEARCH_DEFAULT, defaults.revision)))

    origins.append(InputOrigin("profile", profile.source or Source(SourceKind.USER_FACT, profile.revision)))
    valuations, growth = _resolve_positions(profile, request.inputs, override_layers, origins)
    return ResolvedAnalysis(
        request=request,
        profile=profile,
        plan=_resolve_plan(plan, profile, request.inputs.subject, override_layers, origins),
        assumptions=_select("assumptions", EconomicAssumptions, config_layers, origins),
        preferences=_select("preferences", ModelPreferences, config_layers, origins),
        scenario_revision=scenario.revision if scenario else None,
        preset_revision=preset.revision if preset else None,
        defaults_revision=defaults.revision if defaults else None,
        position_valuations=valuations,
        position_growth=growth,
        origins=tuple(origins),
    )
