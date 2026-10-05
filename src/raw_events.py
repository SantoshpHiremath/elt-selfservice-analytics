"""
Synthetic raw booking/pricing events for the pricing, e-commerce and
tourism/leisure domain (lift passes, hotel rooms, rentals, spa days).

Deliberately shaped like a real upstream event source would be: nested,
inconsistent field naming, occasional nulls, and a couple of duplicate
event deliveries (a very common real-world event-pipeline issue) — the
raw layer an ELT pipeline's Load stage receives before any cleanup, not
an already-tidy table.
"""

import random

PRODUCTS = [
    ("SKI-DAYPASS", "Ski Day Pass", "lift_ticket"),
    ("SKI-SEASON", "Ski Season Pass", "lift_ticket"),
    ("HOTEL-STD", "Standard Room", "accommodation"),
    ("HOTEL-SUITE", "Suite", "accommodation"),
    ("RENTAL-SKI", "Ski Equipment Rental", "rental"),
    ("SPA-DAY", "Spa Day Pass", "wellness"),
]

CHANNELS = ["web", "mobile_app", "partner_api", "call_center"]
REGIONS = ["AT", "CH", "DE", "FR", "IT"]


def _gen_one_event(rng, event_id):
    sku, name, category = rng.choice(PRODUCTS)
    base_price = {"lift_ticket": 55, "accommodation": 140, "rental": 35, "wellness": 60}[category]
    # Realistic price variation: demand-based multiplier plus noise.
    demand_multiplier = rng.choice([0.85, 1.0, 1.0, 1.0, 1.15, 1.3])
    price = round(base_price * demand_multiplier * rng.uniform(0.95, 1.05), 2)
    lead_time = rng.randint(0, 120)
    channel = rng.choice(CHANNELS)

    # Cancellation probability genuinely depends on lead_time, price, and
    # channel — a long-lead-time, expensive, call-center booking is more
    # likely to fall through than a short-lead-time, cheap, web booking.
    # (Directionally realistic synthetic assumptions.) Base
    # rate ~8%, then adjusted by real feature-driven multipliers plus
    # per-event random noise, so the signal is genuine but not perfectly
    # separable — the same "noisy but real signal" discipline for
    # predictive-modeling projects.
    cancel_prob = 0.05
    if lead_time > 60:
        cancel_prob += 0.10
    elif lead_time > 30:
        cancel_prob += 0.04
    if price > base_price * 1.15:
        cancel_prob += 0.06
    if channel == "call_center":
        cancel_prob += 0.05
    elif channel == "partner_api":
        cancel_prob -= 0.02
    cancel_prob = min(max(cancel_prob, 0.01), 0.85)
    cancelled = rng.random() < cancel_prob

    event = {
        "event_id": event_id,
        "sku": sku,
        # Deliberately inconsistent raw field naming across the "event
        # source" — some events use product_name, some don't send it at
        # all (nested/missing-field realism an ELT Load stage has to
        # tolerate, not assume away).
        "product_name": name if rng.random() > 0.1 else None,
        "category": category,
        "channel": channel,
        "region": rng.choice(REGIONS),
        "booked_price_eur": price,
        "quantity": rng.choice([1, 1, 1, 2, 2, 3]),
        "booking_date": f"2026-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}",
        "lead_time_days": lead_time,
        "customer_id": f"CUST-{rng.randint(1000, 4999)}",
        "cancelled": cancelled,
    }
    return event


def generate_raw_events(n=5000, seed=17, duplicate_rate=0.02):
    """Generates n raw booking events, then injects duplicate event
    deliveries at duplicate_rate (a realistic at-least-once delivery
    issue from a real event source) — the Load stage must ingest these
    as-is; de-duplication happens later, in-warehouse, as part of the
    Transform stage, which is the actual point of this project."""
    rng = random.Random(seed)
    events = [_gen_one_event(rng, f"EVT-{i:06d}") for i in range(n)]

    n_dupes = int(n * duplicate_rate)
    for _ in range(n_dupes):
        original = rng.choice(events)
        events.append(dict(original))  # exact duplicate delivery

    rng.shuffle(events)
    return events
