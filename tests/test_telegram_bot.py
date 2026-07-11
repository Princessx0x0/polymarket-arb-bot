"""
Mock tests for src/telegram_bot.py — command routing only, no network. This is the
module whose broken `execute_mutually_exclusive`/`execute_contradiction_arb`/
`execute_one_of_many` import used to crash every /execute* command; these tests
mainly guard against that class of regression by proving the module (and every
strategy it references) imports and its command handlers behave without hitting
Telegram, Polymarket, or GCP.
"""
from src import telegram_bot


def test_cmd_help_lists_every_execute_variant():
    text = telegram_bot.cmd_help()
    for cmd in ["/execute ", "/execute1", "/execute2", "/execute3", "/execute4", "/execute5"]:
        assert cmd in text


def test_cmd_execute_usage_errors_return_without_touching_network():
    assert "Usage" in telegram_bot.cmd_execute(["/execute1"])
    assert "Usage" in telegram_bot.cmd_execute(["/execute2", "slug-a"])
    assert "Usage" in telegram_bot.cmd_execute(["/execute3", "slug-a"])
    assert "Usage" in telegram_bot.cmd_execute(["/execute4"])
    assert "Usage" in telegram_bot.cmd_execute(["/execute5"])


def test_cmd_status_reports_all_five_strategies_loaded():
    assert "Strategies: 1-5 loaded" in telegram_bot.cmd_status()
