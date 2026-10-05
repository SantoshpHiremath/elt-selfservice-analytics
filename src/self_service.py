"""
Self-service analytics layer, on top of the transformed fct_bookings
table: a small set of named, parameterized, pre-validated queries a
business user (e.g. a pricing analyst) could call without writing raw
SQL against the warehouse, empowering business users with data-driven
insights.

The governance angle matters as much as the query layer itself: every
query here is a fixed, reviewed SQL template with a small, explicit set
of allowed parameters — not an open text-to-SQL box a user could point
at arbitrary tables. That's a deliberate, real design choice: true
self-service analytics needs guardrails (a business user asking "revenue
by region" shouldn't be able to accidentally query a PII table or write
an unbounded join), not just SQL access.
"""

ALLOWED_CATEGORIES = {"lift_ticket", "accommodation", "rental", "wellness"}
ALLOWED_REGIONS = {"AT", "CH", "DE", "FR", "IT"}
ALLOWED_CHANNELS = {"web", "mobile_app", "partner_api", "call_center"}


class SelfServiceQueryError(ValueError):
    pass


def revenue_by_region(con, category=None):
    """Total gross revenue and booking count by region, optionally
    filtered to one product category. This is the shape of question a
    pricing analyst asks routinely — it should not require writing SQL."""
    if category is not None and category not in ALLOWED_CATEGORIES:
        raise SelfServiceQueryError(
            f"Unknown category {category!r}. Allowed: {sorted(ALLOWED_CATEGORIES)}"
        )

    where_clause = "WHERE cancelled = FALSE"
    params = []
    if category is not None:
        where_clause += " AND category = ?"
        params.append(category)

    sql = f"""
        SELECT region,
               COUNT(*) AS booking_count,
               ROUND(SUM(gross_revenue_eur), 2) AS total_revenue_eur,
               ROUND(AVG(booked_price_eur), 2) AS avg_price_eur
        FROM fct_bookings
        {where_clause}
        GROUP BY region
        ORDER BY total_revenue_eur DESC
    """
    return con.execute(sql, params).fetchdf()


def channel_performance(con, region=None):
    """Booking volume and cancellation rate by channel — the kind of
    question that needs a join-free, pre-aggregated answer for a
    non-technical user, and needs cancellations handled correctly (as a
    rate, not silently excluded, which a naive self-service query often
    gets wrong by filtering cancelled=FALSE everywhere by default)."""
    if region is not None and region not in ALLOWED_REGIONS:
        raise SelfServiceQueryError(
            f"Unknown region {region!r}. Allowed: {sorted(ALLOWED_REGIONS)}"
        )

    where_clause = "WHERE 1=1"
    params = []
    if region is not None:
        where_clause += " AND region = ?"
        params.append(region)

    sql = f"""
        SELECT channel,
               COUNT(*) AS total_bookings,
               SUM(CASE WHEN cancelled THEN 1 ELSE 0 END) AS cancelled_bookings,
               ROUND(100.0 * SUM(CASE WHEN cancelled THEN 1 ELSE 0 END) / COUNT(*), 1) AS cancellation_rate_pct
        FROM fct_bookings
        {where_clause}
        GROUP BY channel
        ORDER BY total_bookings DESC
    """
    return con.execute(sql, params).fetchdf()


def top_products_by_revenue(con, limit=5):
    """Top N products by gross revenue — limit is validated to a sane
    range so a self-service user can't accidentally request an
    unbounded result set."""
    if not isinstance(limit, int) or not (1 <= limit <= 50):
        raise SelfServiceQueryError("limit must be an integer between 1 and 50")

    sql = """
        SELECT product_name,
               category,
               COUNT(*) AS booking_count,
               ROUND(SUM(gross_revenue_eur), 2) AS total_revenue_eur
        FROM fct_bookings
        WHERE cancelled = FALSE
        GROUP BY product_name, category
        ORDER BY total_revenue_eur DESC
        LIMIT ?
    """
    return con.execute(sql, [limit]).fetchdf()
