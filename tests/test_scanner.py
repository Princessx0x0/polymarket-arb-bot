"""
Mock tests for src/scanner.py. No network, no GCP — requests.get, the BigQuery
client, and notifier.notify_opportunity are all mocked at the boundary so these
exercise the real filter/pagination/cooldown logic instead of live infrastructure.
"""
from unittest.mock import MagicMock

import pytest

from src import scanner
from tests.helpers import make_condition, make_event


@pytest.fixture(autouse=True)
def reset_notify_state():
    """_last_notified is module-level mutable state — isolate tests from each other."""
    scanner._last_notified.clear()
    yield
    scanner._last_notified.clear()


# ── analyse_event ─────────────────────────────────────────────────────────────

def test_analyse_event_computes_profit_for_real_opportunity():
    event = make_event("evt", "Real Arb", [
        make_condition("Q1", yes_price=0.5, no_price=0.5),
        make_condition("Q2", yes_price=0.35, no_price=0.65),
        make_condition("Q3", yes_price=0.2, no_price=0.8),
    ])
    data = scanner.analyse_event(event)
    assert data is not None
    assert data["conditions"] == 3
    assert data["yes_sum"] == pytest.approx(1.05)
    assert data["profit"] == pytest.approx(0.05)


def test_analyse_event_filters_false_arb_above_threshold():
    # 3 conditions, yes_sum=1.8 — classic inflated Win/Draw/Loss shape.
    # max_yes_sum = 1.0 + 3*0.03 = 1.09, so this must be filtered out.
    event = make_event("false-arb", "Match Result", [
        make_condition("A wins", yes_price=0.6, no_price=0.4),
        make_condition("Draw",   yes_price=0.6, no_price=0.4),
        make_condition("B wins", yes_price=0.6, no_price=0.4),
    ])
    assert scanner.analyse_event(event) is None


def test_analyse_event_returns_none_with_no_yes_outcome():
    event = make_event("weird", "No Yes Outcome", [
        {"question": "Q", "outcomes": '["Maybe"]', "outcomePrices": '["0.5"]', "clobTokenIds": '["T"]'},
    ])
    assert scanner.analyse_event(event) is None


# ── fetch_all_negrisk_events ─────────────────────────────────────────────────

def test_fetch_all_negrisk_events_paginates_and_filters(monkeypatch):
    # Page 1: exactly `limit` (100) filler events with too few conditions to be
    # kept, forcing the loop to request a second page.
    page1 = [make_event(f"filler-{i}", "filler", [make_condition("q", 0.5, 0.5)]) for i in range(100)]
    # Page 2: one real NegRisk event with 3 conditions, under the page limit
    # so the loop stops after this.
    real_event = make_event("real-negrisk", "Real Event", [
        make_condition("Q1", 0.3, 0.7),
        make_condition("Q2", 0.3, 0.7),
        make_condition("Q3", 0.3, 0.7),
    ])
    page2 = [real_event]

    mock_get = MagicMock()
    mock_get.side_effect = [
        MagicMock(json=lambda: page1),
        MagicMock(json=lambda: page2),
    ]
    monkeypatch.setattr(scanner.requests, "get", mock_get)

    events = scanner.fetch_all_negrisk_events()

    assert mock_get.call_count == 2
    assert mock_get.call_args_list[0].kwargs["params"]["offset"] == 0
    assert mock_get.call_args_list[1].kwargs["params"]["offset"] == 100
    assert events == [real_event]


# ── _should_notify cooldown ───────────────────────────────────────────────────

def test_should_notify_cooldown(monkeypatch):
    # Start comfortably above the cooldown window so the first call's
    # `now - 0 >= NOTIFY_COOLDOWN_SECS` check passes regardless of the
    # (unset) default last-notified time of 0.
    fake_now = [scanner.NOTIFY_COOLDOWN_SECS * 10]
    monkeypatch.setattr(scanner.time, "time", lambda: fake_now[0])

    assert scanner._should_notify("slug-x") is True
    # Immediately again, still inside the cooldown window.
    assert scanner._should_notify("slug-x") is False

    fake_now[0] += scanner.NOTIFY_COOLDOWN_SECS + 1
    assert scanner._should_notify("slug-x") is True


# ── scan_all ──────────────────────────────────────────────────────────────────

def test_scan_all_notifies_once_per_cooldown_for_real_opportunity(monkeypatch):
    real_event = make_event("real-negrisk", "Real Event", [
        make_condition("Q1", 0.5, 0.5),
        make_condition("Q2", 0.35, 0.65),
        make_condition("Q3", 0.2, 0.8),
    ])
    monkeypatch.setattr(scanner, "fetch_all_negrisk_events", lambda: [real_event])
    monkeypatch.setattr(scanner, "log_opportunity", MagicMock())
    mock_notify = MagicMock()
    monkeypatch.setattr(scanner, "notify_opportunity", mock_notify)

    scanner.scan_all()
    scanner.scan_all()  # same opportunity again, still inside cooldown

    mock_notify.assert_called_once()
    title_arg = mock_notify.call_args.args[0]
    assert title_arg == "Real Event"
