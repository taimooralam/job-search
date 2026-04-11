#!/usr/bin/env python3
"""Check tracked flights and send Telegram alerts. Designed for cron use."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import requests as http_requests

from fli.models import (
    Airport,
    FlightSearchFilters,
    FlightSegment,
    MaxStops,
    PassengerInfo,
    SeatType,
    TripType,
)
from search_utils import fmt_price, search_with_currency

SEAT_MAP = {
    "ECONOMY": SeatType.ECONOMY,
    "PREMIUM_ECONOMY": SeatType.PREMIUM_ECONOMY,
    "BUSINESS": SeatType.BUSINESS,
    "FIRST": SeatType.FIRST,
}

STOPS_MAP = {
    "ANY": MaxStops.ANY,
    "NON_STOP": MaxStops.NON_STOP,
    "ONE_STOP": MaxStops.ONE_STOP_OR_FEWER,
    "TWO_STOPS": MaxStops.TWO_OR_FEWER_STOPS,
}

DATA_DIR = os.environ.get(
    "FLIGHTCLAW_DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
)
TRACKED_FILE = os.path.join(DATA_DIR, "tracked.json")


# ── Telegram (self-contained, best-effort) ��─────────────────────

def send_telegram(message: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        resp = http_requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


# ── Data persistence ─────���──────────────────────────────────────

def load_tracked():
    if not os.path.exists(TRACKED_FILE):
        return []
    with open(TRACKED_FILE, "r") as f:
        return json.load(f)


def save_tracked(tracked):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TRACKED_FILE, "w") as f:
        json.dump(tracked, f, indent=2)


# ── Route check ────��────────────────────────────────────────────

def check_route(entry):
    origin = Airport[entry["origin"]]
    destination = Airport[entry["destination"]]

    segments = [FlightSegment(
        departure_airport=[[origin, 0]],
        arrival_airport=[[destination, 0]],
        travel_date=entry["date"],
    )]
    trip_type = TripType.ONE_WAY

    if entry.get("return_date"):
        segments.append(FlightSegment(
            departure_airport=[[destination, 0]],
            arrival_airport=[[origin, 0]],
            travel_date=entry["return_date"],
        ))
        trip_type = TripType.ROUND_TRIP

    filters = FlightSearchFilters(
        trip_type=trip_type,
        passenger_info=PassengerInfo(adults=1),
        flight_segments=segments,
        seat_type=SEAT_MAP.get(entry.get("cabin", "ECONOMY"), SeatType.ECONOMY),
        stops=STOPS_MAP.get(entry.get("stops", "ANY"), MaxStops.ANY),
    )

    results, currency = search_with_currency(filters, top_n=1)
    if not results:
        return None, None, currency

    flight = results[0]
    if isinstance(flight, tuple):
        flight = flight[0]

    airline = flight.legs[0].airline.name if flight.legs else None
    return round(flight.price, 2), airline, currency


# ── Main ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Check tracked flights with Telegram alerts")
    parser.add_argument("--threshold", type=float, default=10, help="Percentage drop to alert (default: 10)")
    args = parser.parse_args()

    tracked = load_tracked()
    if not tracked:
        print("No flights being tracked.")
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    now_short = datetime.now(timezone.utc).strftime("%H:%M UTC")
    alerts = []

    for entry in tracked:
        route = f"{entry['origin']} -> {entry['destination']} on {entry['date']}"
        currency = entry.get("currency", "USD")
        print(f"Checking {route}...")

        try:
            price, airline, detected_currency = check_route(entry)
            currency = detected_currency or currency
        except Exception as e:
            print(f"  Error: {e}", file=sys.stderr)
            continue

        if price is None:
            print("  No results found")
            continue

        entry["price_history"].append({
            "timestamp": now_iso,
            "best_price": price,
            "airline": airline,
        })
        entry["currency"] = currency

        prev_prices = [p["best_price"] for p in entry["price_history"][:-1] if p["best_price"]]
        if prev_prices:
            last_price = prev_prices[-1]
            change = price - last_price
            pct = (change / last_price) * 100

            if change < 0:
                print(f"  {fmt_price(price, currency)} ({airline}) - DOWN {fmt_price(abs(change), currency)} ({abs(pct):.1f}%)")
                if abs(pct) >= args.threshold:
                    alerts.append({
                        "type": "drop",
                        "route": route,
                        "price": fmt_price(price, currency),
                        "prev": fmt_price(last_price, currency),
                        "pct": f"{abs(pct):.1f}%",
                    })
            elif change > 0:
                print(f"  {fmt_price(price, currency)} ({airline}) - up {fmt_price(change, currency)} ({pct:.1f}%)")
            else:
                print(f"  {fmt_price(price, currency)} ({airline}) - no change")
        else:
            print(f"  {fmt_price(price, currency)} ({airline}) - first price recorded")

        if entry.get("target_price") and price <= entry["target_price"]:
            alerts.append({
                "type": "target",
                "route": route,
                "price": fmt_price(price, currency),
                "target": fmt_price(entry["target_price"], currency),
            })

    save_tracked(tracked)

    if not alerts:
        print("\nNo alerts.")
        return

    # Build Telegram message
    lines = [f"&#9992;&#65039; <b>FlightClaw Alert</b> ({now_short})\n"]
    for a in alerts:
        if a["type"] == "drop":
            lines.append(f"&#128201; <b>PRICE DROP:</b> {a['route']}")
            lines.append(f"   Now: {a['price']} (was {a['prev']}, down {a['pct']})\n")
        elif a["type"] == "target":
            lines.append(f"&#127919; <b>TARGET REACHED:</b> {a['route']}")
            lines.append(f"   Price: {a['price']} (target: {a['target']})\n")

    msg = "\n".join(lines)
    print(f"\nALERTS ({len(alerts)}):")
    print(msg)

    try:
        send_telegram(msg)
    except Exception:
        pass


if __name__ == "__main__":
    main()
