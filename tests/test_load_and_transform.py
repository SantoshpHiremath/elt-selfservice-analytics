import pytest

from src.raw_events import generate_raw_events
from src.load import new_connection, load_raw_events
from src.transform import run_transformations


@pytest.fixture
def loaded_con():
    events = generate_raw_events(n=2000, seed=5)
    con = new_connection()
    load_raw_events(con, events)
    return con, events


class TestLoadStage:
    def test_load_preserves_raw_row_count_including_duplicates(self, loaded_con):
        """Load must not deduplicate or transform anything — that
        belongs to Transform. If Load silently dropped duplicates, this
        wouldn't be ELT anymore."""
        con, events = loaded_con
        raw_count = con.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]
        assert raw_count == len(events)

    def test_load_preserves_nulls_untouched(self, loaded_con):
        con, events = loaded_con
        expected_nulls = sum(1 for e in events if e["product_name"] is None)
        actual_nulls = con.execute(
            "SELECT COUNT(*) FROM raw_events WHERE product_name IS NULL"
        ).fetchone()[0]
        assert actual_nulls == expected_nulls


class TestTransformStage:
    def test_transform_removes_exact_duplicate_events(self, loaded_con):
        con, events = loaded_con
        report = run_transformations(con)
        assert report["duplicates_removed"] > 0
        assert report["transformed_row_count"] == report["raw_row_count"] - report["duplicates_removed"]

    def test_transform_recovers_all_missing_product_names_via_lookup(self, loaded_con):
        con, events = loaded_con
        run_transformations(con)
        still_missing = con.execute(
            "SELECT COUNT(*) FROM fct_bookings WHERE product_name IS NULL"
        ).fetchone()[0]
        assert still_missing == 0

    def test_gross_revenue_equals_price_times_quantity(self, loaded_con):
        con, events = loaded_con
        run_transformations(con)
        mismatches = con.execute(
            "SELECT COUNT(*) FROM fct_bookings "
            "WHERE ABS(gross_revenue_eur - booked_price_eur * quantity) > 0.01"
        ).fetchone()[0]
        assert mismatches == 0

    def test_transformed_table_has_no_duplicate_event_ids(self, loaded_con):
        con, events = loaded_con
        run_transformations(con)
        total = con.execute("SELECT COUNT(*) FROM fct_bookings").fetchone()[0]
        distinct = con.execute("SELECT COUNT(DISTINCT event_id) FROM fct_bookings").fetchone()[0]
        assert total == distinct

    def test_a_genuine_repeat_purchase_with_different_event_id_is_not_collapsed(self):
        """Guards against an overly aggressive dedup: two DIFFERENT
        events (different event_id) that happen to have identical other
        fields (e.g. same customer buying the same product twice) must
        NOT be collapsed into one row — only exact full-row duplicates
        (which in this schema means duplicate event_id, since event_id
        is unique per delivery) should be removed."""
        from src.load import load_raw_events, new_connection
        events = [
            {
                "event_id": "EVT-A", "sku": "SKI-DAYPASS", "product_name": "Ski Day Pass",
                "category": "lift_ticket", "channel": "web", "region": "AT",
                "booked_price_eur": 55.0, "quantity": 1, "booking_date": "2026-01-05",
                "lead_time_days": 10, "customer_id": "CUST-1000", "cancelled": False,
            },
            {
                "event_id": "EVT-B", "sku": "SKI-DAYPASS", "product_name": "Ski Day Pass",
                "category": "lift_ticket", "channel": "web", "region": "AT",
                "booked_price_eur": 55.0, "quantity": 1, "booking_date": "2026-01-05",
                "lead_time_days": 10, "customer_id": "CUST-1000", "cancelled": False,
            },
        ]
        con = new_connection()
        load_raw_events(con, events)
        report = run_transformations(con)
        assert report["transformed_row_count"] == 2
        assert report["duplicates_removed"] == 0
