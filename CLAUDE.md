# CLAUDE.md — Polymarket Arbitrage Bot

This file orients any Claude Code session working in this repo. Read it before touching
`src/`. This is a **money-moving system** — it holds a private key, signs orders, and can
spend real USDC. Treat every change accordingly: a bug here doesn't throw a stack trace in
a log, it loses money or leaves a position half-hedged.

## What this is

A small, always-on bot that finds and executes **Market Rebalancing Arbitrage** on
Polymarket — cases where the sum of "YES" prices across a set of mutually exclusive
conditions drifts away from $1.00, guaranteeing profit if you take the other side before
the market corrects.

The strategy is not a guess — it's grounded in a research paper the project is built from:
**"Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets"** (Saguillo,
Ghafouri, Kiffer, Suarez-Tangil, arXiv:2508.03474). Key facts from that paper that should
shape every engineering decision here:

- Market Rebalancing Arbitrage (single-market, what this bot does) was the most lucrative
  category the paper measured: **$2.7M+ extracted in November 2024 alone**, median profit
  of **~$0.60 per dollar** on single-condition YES+NO mispricings.
- Every trade here is **non-atomic** — legs are placed as separate orders on a CLOB, so a
  multi-condition arb can fill partially and leave you holding an *unhedged* position. This
  is not a hypothetical edge case, it's the normal risk profile of this strategy.
- The paper's own false-positive filter uses a rolling VWAP, a liquidity floor (ignore
  quotes above $0.95 — no real depth left), and a **5% profit floor** to account for
  execution risk. Our current filter (`1.0 + n_conditions * 0.03`, in `src/config.py` as
  `MAX_YES_SUM_SCALE`) is a hand-tuned constant, not derived the same way — treat it as a
  known weak point, not ground truth.
- The paper's own data shows the top arbitrageurs on Polymarket run **thousands of
  automated trades** each. We are not the only bot looking at this. Speed and reliability
  of execution matter more than clever strategy — a correct opportunity found 30 seconds
  late is worth nothing.

If you're about to change strategy logic (`src/execution/executor.py`,
`src/scanner.py`), open the paper section on Market/Combinatorial Arbitrage first. Don't
invent new arbitrage math from intuition — this bot exists because someone already did the
empirical work.

## Architecture

```
┌─────────────────────────────┐
│   Telegram (your phone)      │  /balance /opportunities /positions /execute
└──────────────┬───────────────┘
               │ long-poll HTTPS
┌──────────────▼───────────────────────────────────────────┐
│  GCP e2 VM (small, cheap, always-on — see "Why e2" below)  │
│                                                             │
│  systemd: polymarket-telegram.service                      │
│  ┌────────────────────────────────────────────────────┐    │
│  │ telegram_bot.py — command router, polling loop      │    │
│  └───────┬───────────────────────────────┬────────────┘    │
│          │                               │                  │
│  systemd: polymarket-scanner.service     │                  │
│  ┌───────▼─────────┐            ┌────────▼────────┐         │
│  │ scanner.py       │            │ notifier.py      │         │
│  │ continuous scan, │            │ push alerts to   │         │
│  │ logs to BigQuery │            │ Telegram          │         │
│  └───────┬─────────┘            └──────────────────┘         │
│          │                                                    │
│  ┌───────▼──────────────┐                                    │
│  │ execution/executor.py │  order placement, retries, logging │
│  └───────┬──────────────┘                                    │
│  ┌───────▼──────────────┐                                    │
│  │ execution/client.py   │  CLOB auth (proxy wallet, sig v2)  │
│  └───────┬──────────────┘                                    │
│  ┌───────▼──────────────┐                                    │
│  │ GCP Secret Manager     │  private key, API creds, TG token │
│  └───────────────────────┘                                    │
└──────────────┬─────────────────────────────┬─────────────────┘
               │ HTTPS                        │ streaming inserts
   ┌───────────▼────────────┐      ┌─────────▼──────────┐
   │ Polymarket CLOB / Gamma │      │ BigQuery            │
   │ clob.polymarket.com     │      │ market_ticks_v2      │
   │ gamma-api.polymarket.com│      │ paper_trades          │
   └───────────┬─────────────┘      └──────────────────────┘
               │ on-chain settlement
   ┌───────────▼─────────────┐
   │ Polygon (USDC, cond.     │
   │ tokens, ERC-1155)        │
   └──────────────────────────┘
```

**Why this shape, specifically:**

- **Telegram as the only interface.** No dashboard, no web app. The bot is meant to be
  operated from a phone with zero setup friction — checking a position or firing a trade
  should never require SSH. Every new feature should ask: *can this be a Telegram command
  or alert instead of something you'd need a terminal for?*
- **Scanner and executor are separate processes.** The scanner runs continuously and cheaply
  (market data reads); the executor only runs when a human (or eventually a rule) triggers
  it. Don't merge them — you want the always-on data collection to keep running even if a
  trade attempt is mid-retry, and you don't want scanning cadence coupled to execution
  latency.
- **Secrets never touch disk or env vars.** Everything is pulled from GCP Secret Manager at
  runtime and cached in-process (`src/config.py::Secrets`). Never add a `.env` file with
  real credentials, never hardcode a key "just for testing" — this bot controls a wallet.
- **e2 machine, on purpose, not by accident.** This bot's bottleneck is *market data
  latency and Telegram round-trip*, not compute. An e2-micro/e2-small is enough to run two
  Python processes doing HTTP polling. Before ever suggesting a bigger machine tier, ask
  why — the answer should be a measured CPU/memory ceiling, not "it feels underpowered."
  Scaling this bot means scaling *reliability and speed of decisions*, not instance size.

## Engineering philosophy — always ask why

Every change to this repo should survive these questions before it's written:

1. **Why does this opportunity exist?** Stale quote, thin liquidity, real mispricing? If you
   can't tell the difference in code, the filter is wrong. Don't flag "opportunities" the
   bot can't actually fill at size — see the paper's liquidity floor for the reference
   behavior.
2. **Why is this safe to automate?** Non-atomic execution means partial fills are the norm,
   not the exception. Any code path that places more than one order must answer: what
   happens to my position if order 2 of 5 fails? (Today: `execute_must_happen` logs a
   warning and stops — it does not unwind. That's a deliberate, documented gap, not an
   oversight — know it before extending auto-execution.)
3. **Why this threshold, this constant, this timeout?** `MIN_ORDER_USDC`,
   `MAX_YES_SUM_SCALE`, `SCAN_INTERVAL_SECS` in `src/config.py` are all levers with real
   dollar consequences. If you change one, write down why in the commit message — "tuned by
   trial and error" (see `docs/Challenges.md`) is an honest answer but should be the
   *starting* point for a real derivation, not the permanent justification.
4. **Why does this need a bigger machine / new service / new dependency?** Default answer is
   no. This is a small bot by design (see "Why e2" above). Justify infra growth with a
   measured constraint, not convenience.
5. **Why is this the right place for this logic?** `src/strategy/` exists and is currently
   empty — scan/detect logic is scattered across `scanner.py` and `telegram_bot.py`
   (two separate, *diverging* implementations of the same opportunity scan — see Known
   Gaps). Before adding a sixth place that computes `yes_sum`, ask whether it belongs in
   `strategy/` instead.

## Engineering standards for a betting bot specifically

This is not a CRUD app. Hold it to the standard of software that moves money:

- **Dry-run before live, always.** Every execution function takes a `dry_run` flag for a
  reason — new strategies get proven in `dry_run=True` against real market data before they
  ever get a live path wired to Telegram.
- **Every trade decision is logged structurally**, not just printed. `src/logger.py`
  (`executor_log`) exists so that a failed or incomplete arb is queryable later, not lost in
  a systemd journal. If you add a new execution path, it logs through the same structured
  logger — no bare `print()` for anything that touches an order.
- **Idempotency matters more than cleverness.** Telegram messages can be delivered twice,
  retries can double-fire. Before adding auto-retry or auto-execution, make sure firing the
  same command twice doesn't buy the position twice.
- **No hardcoded paths, usernames, or chat IDs "for now."** They rot the moment the VM is
  rebuilt (which has already happened once — see `docs/Challenges.md`). Config lives in
  `src/config.py` or Secret Manager, not inline in `telegram_bot.py`.
- **Cost discipline is part of correctness.** BigQuery streaming inserts, an always-on VM,
  and polling loops all cost money continuously, separate from trading P&L. A change that
  works but silently triples the BigQuery write volume or adds a second always-on poller is
  not free — think about it the way you'd think about slippage.

## BigQuery — not just a dump, an analysis surface

`market_ticks_v2` and `paper_trades` (schema in `terraform/main.tf`) exist so that arbitrage
detection can be **backtested and tuned against history**, the same way the paper did —
not just as a write-only audit log. When touching the scanner or filter logic:

- Log enough on every scan (yes_sum, condition count, volume, filtered/kept) to later ask
  "would the paper's VWAP+liquidity filter have caught fewer false positives than ours?"
  directly in SQL, without re-running anything live.
- Prefer adding a column to an existing table over adding a new one — fragmenting scan
  history across tables makes exactly this kind of analysis harder later.
- Treat `paper_trades` as the ground truth for "would this filter change have changed our
  decision" experiments before shipping a filter change live.

## Telegram — target state: alerts + one tap, not read + type

Today the bot is pure request/response: you ask, it answers. The goal is closer to how the
paper's top arbitrageurs actually operate — fast, low-friction, low-latency reaction to a
real opportunity:

- `scanner.py` finds opportunities but never calls `notifier.py` — wiring that up (push an
  alert the moment a real, liquidity-filtered opportunity appears) is the single highest-
  leverage change available, bigger than any UI polish.
- Once alerts are real, prefer Telegram inline-keyboard buttons pre-filled with
  slug+budget over asking the user to type a command from memory — cut the round-trip
  between "the bot noticed" and "the trade is placed," since arbitrage windows close.
- Never remove the manual `/execute` path in favor of full auto-fire without an explicit,
  separate decision to do so — see point 2 under "always ask why." Semi-auto (alert + tap
  to confirm) is the safer middle ground until there's a track record.

## Known gaps

**Fixed** (as of the pass that added Strategies 2–4, BigQuery fill logging, and the
notifier wiring):

1. ~~`/execute*` broken end-to-end~~ — `execute_mutually_exclusive`, `execute_contradiction_arb`,
   `execute_one_of_many` are now implemented in `execution/executor.py` (grounded in the
   paper's Definition 3/footnote 6, generalized across markets — see the comment block above
   them for the derivation). The import that used to crash every `/execute*` command is now
   a module-level import in `telegram_bot.py`, so a missing function fails loudly at process
   startup instead of silently inside a command handler.
2. ~~`notifier.py` unwired~~ — `scanner.py::scan_all()` now calls `notify_opportunity()` for
   real, filtered opportunities, with a 30-minute per-slug cooldown (`NOTIFY_COOLDOWN_SECS`,
   config.py) so a long-lived opportunity doesn't re-alert every ~4.5-minute scan cycle.
3. ~~Scan logic duplicated and diverging~~ — the false-arb filter now lives once, inside
   `scanner.py::analyse_event()`. `telegram_bot.py::cmd_opportunities` calls
   `scanner.py`'s `fetch_all_negrisk_events` + `analyse_event` directly instead of
   maintaining its own shallower copy.
4. ~~Fills only lived in Cloud Logging~~ — `execution/executor.py::place_order()` now writes
   every order attempt (filled/failed/skipped) to a new BigQuery `fills` table
   (schema added to `terraform/main.tf`), alongside `paper_trades`, so real execution
   outcomes are queryable against predicted opportunities.
5. `terraform/main.tf`'s secret list was missing `polymarket-funder-address`, which
   `config.py::Secrets.funder_address()` reads at runtime — added.

**Still open:**

1. **No VM is currently running.** The Johannesburg e2 instance was deleted. `terraform/`
   and `restore.sh` already build it — but `terraform apply` needs to run again to create
   the new `fills` table and the `polymarket-funder-address` secret container before any of
   this runs live.
2. **`MAX_YES_SUM_SCALE = 0.03` is still untested against the paper's methodology.** Now
   that fills flow into BigQuery, this is backtestable against `paper_trades` + `fills`
   without needing to run anything live — worth doing before trusting it at higher budgets.
3. **Strategies 2–4 are newly written, unlike 1 and 5 which have 10 real fills behind
   them.** The long-side math (buy both YES when underpriced) is the same proven pattern as
   Strategy 1. The short-side math (buy both NO when overpriced) is new and derived, not
   yet fill-tested — dry-run it first. Both also depend on you correctly asserting that the
   two slugs you pass are genuinely exhaustive+exclusive; the bot cannot verify that.
4. **Telegram alerts are still not one-tap.** `notify_opportunity` now fires, but acting on
   it still means typing a command with the slug and budget by hand. Inline-keyboard
   buttons pre-filled from the alert are the next real "seamless" step.
5. **`docs/ARCHITECTURE.md` / `docs/Architecture.md` collide on a case-insensitive
   filesystem** (both exist in the repo with different casing) — cosmetic, not functional,
   but `git status` on Windows will show a phantom diff until one is removed.
