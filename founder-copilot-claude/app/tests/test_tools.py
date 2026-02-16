from app.tools import execute_tool, should_invoke_tool


def test_unit_economics_tool():
    out = execute_tool("unit_economics_calculator", {"price": 100, "cogs": 30, "cac": 140})
    assert "gross_margin" in out
    assert "cac_payback_periods" in out


def test_tool_gating_market_size():
    assert should_invoke_tool("Help me estimate TAM and market size for fintech", "market_size_lookup")
    assert not should_invoke_tool("How do I create a pitch deck?", "market_size_lookup")


def test_tool_gating_unit_economics():
    assert should_invoke_tool("My CAC is 200 and LTV is 900, what is payback?", "unit_economics_calculator")
    assert should_invoke_tool("price 49, churn 3%, cac 120", "unit_economics_calculator")
    assert not should_invoke_tool("How should I structure my team slide?", "unit_economics_calculator")


def test_stub_tools_are_explicitly_marked_demo():
    market = execute_tool("market_size_lookup", {"market": "ai support tools"})
    comp = execute_tool("competitor_summary", {"company": "Acme"})
    assert market.get("demo_stub") is True
    assert comp.get("demo_stub") is True
