"""
price_history.py - SQLite storage and comparison helpers for gold prices.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path(os.environ.get("HISTORY_DB_PATH", "data/gold_prices.sqlite"))


def store_price_data(
    state_key: str,
    price_data: dict[str, Any],
    *,
    run_date: str,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> None:
    """Persist validated city prices for a state/date."""
    conn = _connect(db_path)
    try:
        _ensure_schema(conn)
        rows = []
        created_at = datetime.now().isoformat(timespec="seconds")
        for city, prices in price_data.get("cities", {}).items():
            source_date = prices.get("_source_date") or price_data.get("cached_date")
            rows.extend(
                [
                    (
                        run_date,
                        state_key,
                        city,
                        "22k",
                        float(prices["22k_per_gram"]),
                        float(prices["22k_per_10g"]),
                        source_date,
                        created_at,
                    ),
                    (
                        run_date,
                        state_key,
                        city,
                        "24k",
                        float(prices["24k_per_gram"]),
                        float(prices["24k_per_10g"]),
                        source_date,
                        created_at,
                    ),
                ]
            )

        conn.executemany(
            """
            INSERT INTO price_history (
                run_date, state_key, city, karat, per_gram, per_10g, source_date, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_date, state_key, city, karat) DO UPDATE SET
                per_gram = excluded.per_gram,
                per_10g = excluded.per_10g,
                source_date = excluded.source_date,
                created_at = excluded.created_at
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def build_history_context(
    state_key: str,
    price_data: dict[str, Any],
    *,
    run_date: str,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Build day-over-day and weekly comparison context from stored data."""
    conn = _connect(db_path)
    try:
        _ensure_schema(conn)
        previous_date = _previous_available_date(conn, state_key, run_date)
        city_comparisons = {}
        if previous_date:
            previous_prices = _prices_for_date(conn, state_key, previous_date)
            for city, current_prices in price_data.get("cities", {}).items():
                prior = previous_prices.get(city, {})
                comparison = {}
                for karat in ("22k", "24k"):
                    current = float(current_prices[f"{karat}_per_gram"])
                    previous = prior.get(karat)
                    if previous is None:
                        continue
                    change = round(current - previous, 2)
                    comparison[karat] = {
                        "previous_per_gram": previous,
                        "current_per_gram": current,
                        "change_per_gram": change,
                        "direction": _direction(change),
                    }
                if comparison:
                    city_comparisons[city] = comparison

        weekly_summary = _weekly_trend_summary(conn, state_key, run_date)
        trend_series = _trend_series(conn, state_key, run_date, price_data)
        return {
            "has_comparison": bool(previous_date and city_comparisons),
            "previous_available_date": previous_date,
            "city_comparisons": city_comparisons,
            "weekly_summary": weekly_summary,
            "trend_series": trend_series,
        }
    finally:
        conn.close()


def _connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            run_date TEXT NOT NULL,
            state_key TEXT NOT NULL,
            city TEXT NOT NULL,
            karat TEXT NOT NULL,
            per_gram REAL NOT NULL,
            per_10g REAL NOT NULL,
            source_date TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (run_date, state_key, city, karat)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_price_history_state_date
        ON price_history (state_key, run_date)
        """
    )
    conn.commit()


def _previous_available_date(conn: sqlite3.Connection, state_key: str, run_date: str) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(run_date) AS previous_date
        FROM price_history
        WHERE state_key = ? AND run_date < ?
        """,
        (state_key, run_date),
    ).fetchone()
    return row["previous_date"] if row and row["previous_date"] else None


def _prices_for_date(conn: sqlite3.Connection, state_key: str, run_date: str) -> dict[str, dict[str, float]]:
    rows = conn.execute(
        """
        SELECT city, karat, per_gram
        FROM price_history
        WHERE state_key = ? AND run_date = ?
        """,
        (state_key, run_date),
    ).fetchall()
    prices: dict[str, dict[str, float]] = {}
    for row in rows:
        prices.setdefault(row["city"], {})[row["karat"]] = float(row["per_gram"])
    return prices


def _weekly_trend_summary(conn: sqlite3.Connection, state_key: str, run_date: str) -> dict[str, Any] | None:
    rows = conn.execute(
        """
        SELECT run_date, karat, AVG(per_gram) AS avg_per_gram
        FROM price_history
        WHERE state_key = ? AND run_date < ?
        GROUP BY run_date, karat
        ORDER BY run_date DESC
        LIMIT 14
        """,
        (state_key, run_date),
    ).fetchall()
    if not rows:
        return None

    by_karat: dict[str, list[sqlite3.Row]] = {"22k": [], "24k": []}
    for row in rows:
        by_karat.setdefault(row["karat"], []).append(row)

    trends = {}
    for karat, karat_rows in by_karat.items():
        ordered = sorted(karat_rows, key=lambda r: r["run_date"])
        if len(ordered) < 2:
            continue
        first = ordered[0]
        last = ordered[-1]
        change = round(float(last["avg_per_gram"]) - float(first["avg_per_gram"]), 2)
        trends[karat] = {
            "first_date": first["run_date"],
            "last_date": last["run_date"],
            "first_avg_per_gram": round(float(first["avg_per_gram"]), 2),
            "last_avg_per_gram": round(float(last["avg_per_gram"]), 2),
            "change_per_gram": change,
            "direction": _direction(change),
            "observations": len(ordered),
        }

    return trends or None


def _trend_series(
    conn: sqlite3.Connection,
    state_key: str,
    run_date: str,
    price_data: dict[str, Any],
    *,
    max_points: int = 7,
) -> list[dict[str, Any]]:
    """Return recent average 22K/24K prices, ending with the current validated run."""
    prior_rows = conn.execute(
        """
        SELECT run_date, karat, AVG(per_gram) AS avg_per_gram
        FROM price_history
        WHERE state_key = ? AND run_date < ?
        GROUP BY run_date, karat
        ORDER BY run_date DESC
        LIMIT ?
        """,
        (state_key, run_date, (max_points - 1) * 2),
    ).fetchall()

    by_date: dict[str, dict[str, float]] = {}
    for row in prior_rows:
        by_date.setdefault(row["run_date"], {})[row["karat"]] = round(float(row["avg_per_gram"]), 2)

    current = _current_average_prices(price_data)
    if current:
        by_date[run_date] = current

    series = [
        {"date": date_key, **values}
        for date_key, values in sorted(by_date.items())
        if "22k" in values and "24k" in values
    ]
    return series[-max_points:]


def _current_average_prices(price_data: dict[str, Any]) -> dict[str, float] | None:
    cities = price_data.get("cities", {})
    if not cities:
        return None

    totals = {"22k": 0.0, "24k": 0.0}
    count = 0
    for prices in cities.values():
        try:
            totals["22k"] += float(prices["22k_per_gram"])
            totals["24k"] += float(prices["24k_per_gram"])
            count += 1
        except (KeyError, TypeError, ValueError):
            continue

    if not count:
        return None
    return {
        "22k": round(totals["22k"] / count, 2),
        "24k": round(totals["24k"] / count, 2),
    }


def _direction(change: float) -> str:
    if change > 0:
        return "increased"
    if change < 0:
        return "decreased"
    return "unchanged"
