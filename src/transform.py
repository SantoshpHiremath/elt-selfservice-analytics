"""
ELT Transform stage: everything here runs as SQL against the warehouse
(DuckDB), operating on the already-loaded `raw_events` table — this is
the "T happens after L, in the warehouse" pattern that distinguishes ELT
from ETL, where raw data is loaded first and cleaning/modeling logic runs
as SQL transformations against the loaded data, not in an external Python
preprocessing step before load.

Two problems the raw layer has, both handled here rather than during
Load: (1) duplicate event deliveries, (2) missing product_name on ~10%
of rows (recovered via a lookup join, not dropped).
"""

PRODUCT_LOOKUP_SQL = """
CREATE OR REPLACE TABLE dim_product AS
SELECT * FROM (VALUES
    ('SKI-DAYPASS', 'Ski Day Pass', 'lift_ticket'),
    ('SKI-SEASON', 'Ski Season Pass', 'lift_ticket'),
    ('HOTEL-STD', 'Standard Room', 'accommodation'),
    ('HOTEL-SUITE', 'Suite', 'accommodation'),
    ('RENTAL-SKI', 'Ski Equipment Rental', 'rental'),
    ('SPA-DAY', 'Spa Day Pass', 'wellness')
) AS t(sku, product_name, category)
"""

DEDUPE_AND_ENRICH_SQL = """
CREATE OR REPLACE TABLE fct_bookings AS
WITH deduped AS (
    -- Exact-duplicate event deliveries collapse to one row each,
    -- keeping event_id as the natural key. A real event source
    -- delivering the same event twice (at-least-once delivery) is
    -- exactly what this collapses; a customer genuinely booking the
    -- same SKU twsame day is NOT collapsed, because it would have a
    -- different event_id.
    SELECT DISTINCT * FROM raw_events
)
SELECT
    d.event_id,
    d.sku,
    -- Recover missing product_name from the lookup table instead of
    -- dropping the row — the raw layer's ~10% missing product_name
    -- rate is a gap this transform closes, not a rows-lost problem.
    COALESCE(d.product_name, p.product_name) AS product_name,
    COALESCE(d.category, p.category) AS category,
    d.channel,
    d.region,
    d.booked_price_eur,
    d.quantity,
    d.booked_price_eur * d.quantity AS gross_revenue_eur,
    CAST(d.booking_date AS DATE) AS booking_date,
    d.lead_time_days,
    d.customer_id,
    d.cancelled
FROM deduped d
LEFT JOIN dim_product p ON d.sku = p.sku
"""


def run_transformations(con):
    """Runs the Transform stage against whatever is currently in
    raw_events. Returns a small report of what changed, for a
    transparent 'here's what Transform actually did' record."""
    raw_count = con.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]

    con.execute(PRODUCT_LOOKUP_SQL)
    con.execute(DEDUPE_AND_ENRICH_SQL)

    fct_count = con.execute("SELECT COUNT(*) FROM fct_bookings").fetchone()[0]
    still_missing_product_name = con.execute(
        "SELECT COUNT(*) FROM fct_bookings WHERE product_name IS NULL"
    ).fetchone()[0]

    return {
        "raw_row_count": raw_count,
        "transformed_row_count": fct_count,
        "duplicates_removed": raw_count - fct_count,
        "product_name_still_missing_after_lookup": still_missing_product_name,
    }
