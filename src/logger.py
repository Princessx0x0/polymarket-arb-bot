"""
Structured logging for the Polymarket Arbitrage Bot.
Logs to stdout in JSON format — Cloud Logging picks this up automatically.
Every order, scan, and error is logged with full context.
"""
import json
import logging
import sys
from datetime import datetime, timezone

class StructuredLogger:
    def __init__(self, service: str):
        self.service = service

    def _log(self, severity: str, message: str, **kwargs):
        entry = {
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "severity":   severity,
            "service":    self.service,
            "message":    message,
            **kwargs
        }
        print(json.dumps(entry), flush=True)

    def info(self, message: str, **kwargs):
        self._log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log("ERROR", message, **kwargs)

    def order_placed(self, market: str, side: str, price: float,
                     size: float, token_id: str, result: str, error: str = None):
        """Log every order attempt with full context."""
        self._log(
            "INFO" if result == "filled" else "ERROR",
            f"ORDER_{result.upper()}",
            market=market,
            side=side,
            price=price,
            size_usdc=size,
            token_id=token_id[:16] + "...",
            result=result,
            error=error,
        )

    def execution_summary(self, slug: str, strategy: int,
                          budget: float, filled: int,
                          failed: int, skipped: int, profit_pct: float):
        """Log execution summary after every trade."""
        total = filled + failed + skipped
        fill_rate = (filled / total * 100) if total > 0 else 0
        self._log(
            "INFO" if fill_rate == 100 else "WARNING",
            "EXECUTION_SUMMARY",
            slug=slug,
            strategy=f"Strategy{strategy}",
            budget_usdc=budget,
            filled=filled,
            failed=failed,
            skipped=skipped,
            fill_rate_pct=round(fill_rate, 1),
            profit_pct=round(profit_pct, 2),
            complete_arb=fill_rate == 100,
        )

    def opportunity(self, slug: str, title: str, profit_pct: float,
                    conditions: int, yes_sum: float):
        """Log every detected opportunity."""
        self._log(
            "INFO",
            "OPPORTUNITY",
            slug=slug,
            title=title[:60],
            profit_pct=round(profit_pct, 2),
            conditions=conditions,
            yes_sum=round(yes_sum, 4),
        )

    def scan_complete(self, total_scanned: int, opportunities: int, duration_secs: float):
        """Log scanner cycle completion."""
        self._log(
            "INFO",
            "SCAN_COMPLETE",
            total_scanned=total_scanned,
            opportunities_found=opportunities,
            duration_secs=round(duration_secs, 1),
        )

    def health(self, status: str, **kwargs):
        """Log health check status."""
        self._log("INFO", f"HEALTH_{status.upper()}", **kwargs)

# Module-level loggers
scanner_log = StructuredLogger("polymarket-scanner")
bot_log     = StructuredLogger("polymarket-bot")
executor_log = StructuredLogger("polymarket-executor")
