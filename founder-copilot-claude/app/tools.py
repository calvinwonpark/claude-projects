import math
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "market_size_lookup": ToolSpec(
        name="market_size_lookup",
        description="DEMO_ONLY: market sizing placeholder (replace with real data provider in production).",
        input_schema={"type": "object", "properties": {"market": {"type": "string"}}, "required": ["market"]},
    ),
    "competitor_summary": ToolSpec(
        name="competitor_summary",
        description="DEMO_ONLY: competitor analysis placeholder (replace with real market intelligence source).",
        input_schema={"type": "object", "properties": {"company": {"type": "string"}}, "required": ["company"]},
    ),
    "unit_economics_calculator": ToolSpec(
        name="unit_economics_calculator",
        description="Compute contribution margin and payback period.",
        input_schema={
            "type": "object",
            "properties": {
                "price": {"type": "number"},
                "cogs": {"type": "number"},
                "cac": {"type": "number"},
                "gross_margin": {"type": "number"},
            },
            "required": ["price", "cogs", "cac"],
        },
    ),
}


def plan_tool_for_query(query: str) -> str | None:
    q = (query or "").lower()
    if any(k in q for k in ["tam", "market size", "serviceable market"]):
        return "market_size_lookup"
    if any(k in q for k in ["competitor", "competitive", "alternatives"]):
        return "competitor_summary"
    if any(k in q for k in ["unit economics", "payback", "cac", "ltv"]):
        return "unit_economics_calculator"
    return None


def anthropic_tools() -> list[dict[str, Any]]:
    return [
        {"name": spec.name, "description": spec.description, "input_schema": spec.input_schema}
        for spec in TOOL_REGISTRY.values()
    ]


def _has_market_intent(q: str) -> bool:
    checks = ["tam", "sam", "som", "market size", "how big is the market", "market sizing"]
    return any(c in q for c in checks)


def _has_unit_econ_intent(q: str) -> bool:
    checks = ["cac", "ltv", "unit economics", "margin", "payback", "pricing model", "churn", "pricing"]
    if any(c in q for c in checks):
        return True
    # Numeric financial style input hints.
    numeric_hits = re.findall(r"\b\d+(?:\.\d+)?\b", q)
    has_numeric = len(numeric_hits) >= 2
    has_fin_tokens = any(t in q for t in ["price", "cogs", "cac", "ltv", "arpu", "churn"])
    return has_numeric and has_fin_tokens


def should_invoke_tool(query: str, tool_name: str) -> bool:
    q = (query or "").lower()
    if tool_name == "market_size_lookup":
        return _has_market_intent(q)
    if tool_name == "unit_economics_calculator":
        return _has_unit_econ_intent(q)
    if tool_name == "competitor_summary":
        return any(k in q for k in ["competitor", "competitive", "alternatives", "competitor analysis"])
    return False


def allowed_tools_for_query(query: str) -> list[dict[str, Any]]:
    allowed_names = [name for name in TOOL_REGISTRY if should_invoke_tool(query, name)]
    return [
        {"name": spec.name, "description": spec.description, "input_schema": spec.input_schema}
        for spec in TOOL_REGISTRY.values()
        if spec.name in allowed_names
    ]


def _validate_number(value: Any, key: str) -> float:
    try:
        return float(value)
    except Exception:
        raise ValueError(f"{key} must be numeric")


def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOL_REGISTRY:
        raise ValueError(f"Tool not allowed: {name}")
    if not isinstance(args, dict):
        raise ValueError("Tool args must be an object")

    if name == "market_size_lookup":
        market = str(args.get("market", "")).strip()
        if not market:
            raise ValueError("market is required")
        return {
            "market": market,
            "estimate_usd_b": 12.5,
            "demo_stub": True,
            "note": "Demo placeholder estimate. Replace with production market data sources.",
        }

    if name == "competitor_summary":
        company = str(args.get("company", "")).strip()
        if not company:
            raise ValueError("company is required")
        return {
            "company": company,
            "summary": f"{company} focuses on SMB workflows and competes on ease-of-use and lower onboarding friction.",
            "demo_stub": True,
            "note": "Demo placeholder competitor summary. Replace with real data sources in production.",
        }

    if name == "unit_economics_calculator":
        price = _validate_number(args.get("price"), "price")
        cogs = _validate_number(args.get("cogs"), "cogs")
        cac = _validate_number(args.get("cac"), "cac")
        margin = (price - cogs) / price if price > 0 else 0.0
        if args.get("gross_margin") is not None:
            margin = _validate_number(args.get("gross_margin"), "gross_margin")
        contribution = price * margin
        payback_months = (cac / contribution) if contribution > 0 else math.inf
        return {
            "gross_margin": round(margin, 4),
            "contribution_per_period": round(contribution, 2),
            "cac_payback_periods": round(payback_months, 2) if math.isfinite(payback_months) else None,
        }

    raise ValueError(f"Unhandled tool: {name}")
