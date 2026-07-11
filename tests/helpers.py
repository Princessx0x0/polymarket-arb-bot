"""
Shared builders for Gamma-API-shaped test fixtures.

Polymarket's Gamma API returns `outcomes`, `outcomePrices`, and `clobTokenIds` as
JSON-encoded strings, not native lists — parse_markets()/analyse_event() both handle
that. These builders reproduce the real shape so tests exercise the actual parsing
path instead of a shortcut.
"""
import json


def make_condition(question, yes_price, no_price, yes_token="YES_TOK", no_token="NO_TOK"):
    return {
        "question": question,
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps([str(yes_price), str(no_price)]),
        "clobTokenIds": json.dumps([yes_token, no_token]),
    }


def make_event(slug, title, conditions, neg_risk=True, volume=1000.0):
    return {
        "slug": slug,
        "title": title,
        "negRisk": neg_risk,
        "volume24hr": volume,
        "markets": conditions,
    }
