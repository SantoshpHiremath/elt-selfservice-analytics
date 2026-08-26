"""
ELT Load stage: raw events go into the warehouse AS-IS, before any
cleaning or transformation — this is the actual architectural point of
ELT versus ETL. In ETL, you'd clean/transform in an external process
before loading. Here, the raw, messy, duplicate-containing event data
lands in a `raw_events` table in DuckDB completely untouched, and every
transformation happens afterward with in-warehouse SQL (see
`transform.py`) — the same pattern a real cloud data warehouse (BigQuery,
Snowflake, Redshift) ELT pipeline uses, at a scale runnable locally.
"""

import duckdb


def load_raw_events(con, events):
    """Creates raw_events and loads the event dicts exactly as received
    — nulls, duplicates, and inconsistent fields all included, untouched.
    This is intentionally the least interesting function in the project:
    Load should not transform anything, or it isn't ELT."""
    con.execute("""
        CREATE OR REPLACE TABLE raw_events (
            event_id VARCHAR,
            sku VARCHAR,
            product_name VARCHAR,
            category VARCHAR,
            channel VARCHAR,
            region VARCHAR,
            booked_price_eur DOUBLE,
            quantity INTEGER,
            booking_date VARCHAR,
            lead_time_days INTEGER,
            customer_id VARCHAR,
            cancelled BOOLEAN
        )
    """)

    con.executemany(
        """
        INSERT INTO raw_events VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                e["event_id"], e["sku"], e["product_name"], e["category"],
                e["channel"], e["region"], e["booked_price_eur"], e["quantity"],
                e["booking_date"], e["lead_time_days"], e["customer_id"], e["cancelled"],
            )
            for e in events
        ],
    )
    return con.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]


def new_connection(db_path=":memory:"):
    return duckdb.connect(db_path)
