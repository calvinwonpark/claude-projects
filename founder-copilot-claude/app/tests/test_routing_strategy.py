from dataclasses import replace

import app.router.router as router_module
from app.config import settings
from app.router.strategies import AgentCandidate, winner_take_all
from app.router.router import route_query


def test_winner_take_all_selects_highest():
    out = winner_take_all(
        [
            AgentCandidate(label="marketing", confidence=0.2),
            AgentCandidate(label="tech", confidence=0.6),
            AgentCandidate(label="investor", confidence=0.4),
        ]
    )
    assert out["selected_agent"] == "tech"


def test_route_query_includes_strategy_selection_fields():
    out = route_query("How should I plan fundraising runway and KPI narrative?")
    assert "strategy_selected" in out
    assert "selection_reason" in out
    assert out["strategy_selected"] in {"winner_take_all", "consult_then_decide", "ensemble_vote"}


def test_auto_consult_then_decide_for_mixed_signals(monkeypatch):
    auto_settings = replace(settings, router=replace(settings.router, strategy="auto"))
    monkeypatch.setattr(router_module, "settings", auto_settings)
    out = route_query("For fundraising, should we prioritize API reliability or GTM messaging first?")
    assert out["strategy_selected"] == "consult_then_decide"


def test_auto_ensemble_vote_for_ambiguous_query(monkeypatch):
    auto_settings = replace(settings, router=replace(settings.router, strategy="auto"))
    monkeypatch.setattr(router_module, "settings", auto_settings)
    out = route_query("Give me a plan for next quarter priorities.")
    assert out["strategy_selected"] == "ensemble_vote"
