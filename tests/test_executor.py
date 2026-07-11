"""
Mock tests for src/execution/executor.py. No network, no GCP, no live CLOB client —
fetch_event, place_order's CLOB client, and BigQuery's log_fill are mocked at the
boundary so these exercise the real arbitrage math (Strategies 1-5) instead of live
infrastructure.
"""
from unittest.mock import MagicMock

import pytest

from src.execution import executor
from tests.helpers import make_condition, make_event


# ── parse_markets ─────────────────────────────────────────────────────────────

def test_parse_markets_extracts_prices_and_tokens():
    event = make_event("evt", "Title", [
        make_condition("Will A win?", yes_price=0.4, no_price=0.55, yes_token="YA", no_token="NA"),
        make_condition("Will B win?", yes_price=0.3, no_price=0.65, yes_token="YB", no_token="NB"),
    ])
    markets = executor.parse_markets(event)
    assert len(markets) == 2
    assert markets[0]["yes_price"] == 0.4
    assert markets[0]["yes_token"] == "YA"
    assert markets[0]["no_token"] == "NA"
    assert markets[1]["no_price"] == pytest.approx(0.65)


# ── place_order ───────────────────────────────────────────────────────────────

def test_place_order_below_minimum_is_skipped_and_logged(monkeypatch):
    mock_log_fill = MagicMock()
    monkeypatch.setattr(executor, "log_fill", mock_log_fill)

    result = executor.place_order(None, "TOK", 0.5, 0.5, dry_run=False, label="x")

    assert result == "skipped"
    mock_log_fill.assert_called_once_with("", 0, "TOK", 0.5, 0.5, "skipped", "below_minimum")


def test_place_order_dry_run_never_writes_to_bigquery(monkeypatch):
    mock_log_fill = MagicMock()
    monkeypatch.setattr(executor, "log_fill", mock_log_fill)

    result = executor.place_order(None, "TOK", 0.5, 10.0, dry_run=True, label="x")

    assert result == "filled"
    mock_log_fill.assert_not_called()  # a dry-run "fill" isn't a real trade


def test_place_order_live_success_logs_fill(monkeypatch):
    mock_log_fill = MagicMock()
    monkeypatch.setattr(executor, "log_fill", mock_log_fill)
    client = MagicMock()
    client.create_and_post_order.return_value = {"id": "order-1"}

    result = executor.place_order(client, "TOK", 0.5, 10.0, dry_run=False,
                                   label="x", slug="s", strategy=1)

    assert result == "filled"
    client.create_and_post_order.assert_called_once()
    mock_log_fill.assert_called_once_with("s", 1, "TOK", 0.5, 10.0, "filled")


def test_place_order_retries_once_then_fails(monkeypatch):
    monkeypatch.setattr(executor.time, "sleep", lambda s: None)
    mock_log_fill = MagicMock()
    monkeypatch.setattr(executor, "log_fill", mock_log_fill)
    client = MagicMock()
    client.create_and_post_order.side_effect = [Exception("boom1"), Exception("boom2")]

    result = executor.place_order(client, "TOK", 0.5, 10.0, dry_run=False,
                                   label="x", slug="s", strategy=1)

    assert result == "failed"
    assert client.create_and_post_order.call_count == 2
    mock_log_fill.assert_called_once_with("s", 1, "TOK", 0.5, 10.0, "failed", "boom2")


# ── Strategy 1: Basic Arb ─────────────────────────────────────────────────────

def test_execute_basic_arb_buys_both_legs_when_underpriced(monkeypatch):
    event = make_event("evt-a", "Some Market", [
        make_condition("Will it happen?", yes_price=0.45, no_price=0.50, yes_token="Y1", no_token="N1"),
    ])
    monkeypatch.setattr(executor, "fetch_event", lambda slug: event)
    mock_place = MagicMock(return_value="filled")
    monkeypatch.setattr(executor, "place_order", mock_place)

    executor.execute_basic_arb("evt-a", budget_usdc=10.0, dry_run=True)

    assert mock_place.call_count == 2
    tokens = {c.args[1] for c in mock_place.call_args_list}
    assert tokens == {"Y1", "N1"}
    for c in mock_place.call_args_list:
        assert c.args[3] == pytest.approx(5.0)  # half the budget per leg
        assert c.kwargs["slug"] == "evt-a"
        assert c.kwargs["strategy"] == 1


def test_execute_basic_arb_skips_fairly_priced_market(monkeypatch):
    event = make_event("evt-fair", "Fair Market", [
        make_condition("Q", yes_price=0.5, no_price=0.5),
    ])
    monkeypatch.setattr(executor, "fetch_event", lambda slug: event)
    mock_place = MagicMock()
    monkeypatch.setattr(executor, "place_order", mock_place)

    executor.execute_basic_arb("evt-fair", budget_usdc=10.0, dry_run=True)

    mock_place.assert_not_called()


# ── Strategy 5: Must-Happen ───────────────────────────────────────────────────

def test_execute_must_happen_filters_false_arb(monkeypatch):
    conditions = [
        make_condition("A wins", yes_price=0.6, no_price=0.4, yes_token="YA", no_token="NA"),
        make_condition("Draw",   yes_price=0.6, no_price=0.4, yes_token="YD", no_token="ND"),
        make_condition("B wins", yes_price=0.6, no_price=0.4, yes_token="YB", no_token="NB"),
    ]
    event = make_event("false-arb-evt", "Match Result", conditions)
    monkeypatch.setattr(executor, "fetch_event", lambda slug: event)
    mock_place = MagicMock()
    monkeypatch.setattr(executor, "place_order", mock_place)

    result = executor.execute_must_happen("false-arb-evt", budget_usdc=30.0, dry_run=True)

    mock_place.assert_not_called()
    assert result is None


def test_execute_must_happen_buys_no_on_every_condition(monkeypatch):
    conditions = [
        make_condition("Q1", yes_price=0.5,  no_price=0.5,  yes_token="Y1", no_token="N1"),
        make_condition("Q2", yes_price=0.35, no_price=0.65, yes_token="Y2", no_token="N2"),
        make_condition("Q3", yes_price=0.2,  no_price=0.8,  yes_token="Y3", no_token="N3"),
    ]
    event = make_event("real-arb-evt", "Real Opportunity", conditions)
    monkeypatch.setattr(executor, "fetch_event", lambda slug: event)
    mock_place = MagicMock(return_value="filled")
    monkeypatch.setattr(executor, "place_order", mock_place)

    filled = executor.execute_must_happen("real-arb-evt", budget_usdc=30.0, dry_run=True)

    assert filled == 3
    tokens = {c.args[1] for c in mock_place.call_args_list}
    assert tokens == {"N1", "N2", "N3"}
    for c in mock_place.call_args_list:
        assert c.args[3] == pytest.approx(10.0)  # 30 / 3 conditions
        assert c.kwargs["strategy"] == 5


# ── Strategies 2 & 3: Complementary Cross-Market Pairs ───────────────────────

def test_execute_contradiction_arb_long_case_buys_both_yes(monkeypatch):
    events = {
        "slug-a": make_event("slug-a", "A", [make_condition("Q", 0.3, 0.7, "YA", "NA")]),
        "slug-b": make_event("slug-b", "B", [make_condition("Q", 0.4, 0.6, "YB", "NB")]),
    }
    monkeypatch.setattr(executor, "fetch_event", lambda slug: events[slug])
    mock_place = MagicMock(return_value="filled")
    monkeypatch.setattr(executor, "place_order", mock_place)

    executor.execute_contradiction_arb("slug-a", "slug-b", budget_usdc=10.0, dry_run=True)

    # yes_a + yes_b = 0.7 < 1 -> jointly underpriced, buy both YES.
    tokens = {c.args[1] for c in mock_place.call_args_list}
    assert tokens == {"YA", "YB"}
    for c in mock_place.call_args_list:
        assert c.args[3] == pytest.approx(5.0)


def test_execute_contradiction_arb_short_case_buys_both_no(monkeypatch):
    events = {
        "slug-a": make_event("slug-a", "A", [make_condition("Q", 0.65, 0.35, "YA", "NA")]),
        "slug-b": make_event("slug-b", "B", [make_condition("Q", 0.55, 0.45, "YB", "NB")]),
    }
    monkeypatch.setattr(executor, "fetch_event", lambda slug: events[slug])
    mock_place = MagicMock(return_value="filled")
    monkeypatch.setattr(executor, "place_order", mock_place)

    executor.execute_contradiction_arb("slug-a", "slug-b", budget_usdc=10.0, dry_run=True)

    # yes_a + yes_b = 1.2 > 1 -> jointly overpriced, buy both NO instead.
    tokens = {c.args[1] for c in mock_place.call_args_list}
    assert tokens == {"NA", "NB"}


def test_execute_mutually_exclusive_shares_the_same_math(monkeypatch):
    events = {
        "slug-a": make_event("slug-a", "A", [make_condition("Q", 0.3, 0.7, "YA", "NA")]),
        "slug-b": make_event("slug-b", "B", [make_condition("Q", 0.4, 0.6, "YB", "NB")]),
    }
    monkeypatch.setattr(executor, "fetch_event", lambda slug: events[slug])
    mock_place = MagicMock(return_value="filled")
    monkeypatch.setattr(executor, "place_order", mock_place)

    executor.execute_mutually_exclusive("slug-a", "slug-b", budget_usdc=10.0, dry_run=True)

    tokens = {c.args[1] for c in mock_place.call_args_list}
    assert tokens == {"YA", "YB"}
    for c in mock_place.call_args_list:
        assert c.kwargs["strategy"] == 2  # distinct strategy id from Strategy 3


# ── Strategy 4: One-of-Many ───────────────────────────────────────────────────

def test_execute_one_of_many_long_case_buys_yes_on_all(monkeypatch):
    events = {
        "s1": make_event("s1", "A", [make_condition("Q", 0.2, 0.8, "Y1", "N1")]),
        "s2": make_event("s2", "B", [make_condition("Q", 0.3, 0.7, "Y2", "N2")]),
        "s3": make_event("s3", "C", [make_condition("Q", 0.25, 0.75, "Y3", "N3")]),
    }
    monkeypatch.setattr(executor, "fetch_event", lambda slug: events[slug])
    mock_place = MagicMock(return_value="filled")
    monkeypatch.setattr(executor, "place_order", mock_place)

    filled = executor.execute_one_of_many(["s1", "s2", "s3"], budget_usdc=30.0, dry_run=True)

    # yes_sum = 0.75 < 1 -> buy YES on all three.
    assert filled == 3
    tokens = {c.args[1] for c in mock_place.call_args_list}
    assert tokens == {"Y1", "Y2", "Y3"}


def test_execute_one_of_many_short_case_buys_no_on_all(monkeypatch):
    events = {
        "s1": make_event("s1", "A", [make_condition("Q", 0.5, 0.5, "Y1", "N1")]),
        "s2": make_event("s2", "B", [make_condition("Q", 0.4, 0.6, "Y2", "N2")]),
        "s3": make_event("s3", "C", [make_condition("Q", 0.35, 0.65, "Y3", "N3")]),
    }
    monkeypatch.setattr(executor, "fetch_event", lambda slug: events[slug])
    mock_place = MagicMock(return_value="filled")
    monkeypatch.setattr(executor, "place_order", mock_place)

    executor.execute_one_of_many(["s1", "s2", "s3"], budget_usdc=30.0, dry_run=True)

    # yes_sum = 1.25 > 1 -> buy NO on all three.
    tokens = {c.args[1] for c in mock_place.call_args_list}
    assert tokens == {"N1", "N2", "N3"}


def test_execute_one_of_many_needs_at_least_two_markets(monkeypatch):
    events = {"s1": make_event("s1", "A", [make_condition("Q", 0.5, 0.5, "Y1", "N1")])}
    monkeypatch.setattr(executor, "fetch_event", lambda slug: events.get(slug))
    mock_place = MagicMock()
    monkeypatch.setattr(executor, "place_order", mock_place)

    result = executor.execute_one_of_many(["s1", "missing-slug"], budget_usdc=30.0, dry_run=True)

    assert result is None
    mock_place.assert_not_called()
