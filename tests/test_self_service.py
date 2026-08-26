import pytest

from src.raw_events import generate_raw_events
from src.load import new_connection, load_raw_events
from src.transform import run_transformations
from src.self_service import (
    revenue_by_region, channel_performance, top_products_by_revenue, SelfServiceQueryError,
)


@pytest.fixture
def con():
    events = generate_raw_events(n=2000, seed=11)
    c = new_connection()
    load_raw_events(c, events)
    run_transformations(c)
    return c


class TestRevenueByRegion:
    def test_returns_one_row_per_region_present_in_data(self, con):
        df = revenue_by_region(con)
        distinct_regions = con.execute(
            "SELECT COUNT(DISTINCT region) FROM fct_bookings"
        ).fetchone()[0]
        assert len(df) == distinct_regions

    def test_excludes_cancelled_bookings_from_revenue(self, con):
        df_all = revenue_by_region(con)
        total_from_query = df_all["total_revenue_eur"].sum()
        manual_total = con.execute(
            "SELECT SUM(gross_revenue_eur) FROM fct_bookings WHERE cancelled = FALSE"
        ).fetchone()[0]
        assert total_from_query == pytest.approx(manual_total, rel=1e-6)

    def test_invalid_category_rejected_not_silently_ignored(self, con):
        with pytest.raises(SelfServiceQueryError, match="Unknown category"):
            revenue_by_region(con, category="not_a_real_category")

    def test_valid_category_filter_narrows_results(self, con):
        df_filtered = revenue_by_region(con, category="wellness")
        manual = con.execute(
            "SELECT SUM(gross_revenue_eur) FROM fct_bookings "
            "WHERE cancelled = FALSE AND category = 'wellness'"
        ).fetchone()[0]
        assert df_filtered["total_revenue_eur"].sum() == pytest.approx(manual, rel=1e-6)


class TestChannelPerformance:
    def test_cancellation_rate_computed_correctly_not_just_excluded(self, con):
        """A naive self-service query might silently filter cancelled=FALSE
        everywhere, which would make cancellation rate unanswerable —
        this query must include cancelled bookings in the count and
        compute a real rate."""
        df = channel_performance(con)
        for _, row in df.iterrows():
            expected_rate = round(100.0 * row["cancelled_bookings"] / row["total_bookings"], 1)
            assert row["cancellation_rate_pct"] == pytest.approx(expected_rate, abs=0.05)

    def test_invalid_region_rejected(self, con):
        with pytest.raises(SelfServiceQueryError, match="Unknown region"):
            channel_performance(con, region="XX")


class TestTopProductsByRevenue:
    def test_results_sorted_descending_by_revenue(self, con):
        df = top_products_by_revenue(con, limit=10)
        revenues = df["total_revenue_eur"].tolist()
        assert revenues == sorted(revenues, reverse=True)

    def test_limit_respected(self, con):
        df = top_products_by_revenue(con, limit=2)
        assert len(df) <= 2

    def test_limit_out_of_range_rejected(self, con):
        with pytest.raises(SelfServiceQueryError):
            top_products_by_revenue(con, limit=500)

    def test_limit_zero_rejected(self, con):
        with pytest.raises(SelfServiceQueryError):
            top_products_by_revenue(con, limit=0)

    def test_non_integer_limit_rejected(self, con):
        with pytest.raises(SelfServiceQueryError):
            top_products_by_revenue(con, limit="five")
