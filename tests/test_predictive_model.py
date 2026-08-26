import pytest

from src.raw_events import generate_raw_events
from src.load import new_connection, load_raw_events
from src.transform import run_transformations
from src.predictive_model import build_training_frame, train_cancellation_model, find_threshold_for_target_recall


@pytest.fixture
def training_df():
    events = generate_raw_events(n=5000, seed=17)
    con = new_connection()
    load_raw_events(con, events)
    run_transformations(con)
    return build_training_frame(con)


class TestCancellationModel:
    def test_auc_is_genuine_signal_not_random_and_not_suspiciously_perfect(self, training_df):
        """The first version of this model had cancellation generated
        with zero relationship to any feature, and scored AUC ~0.52 —
        barely above the 0.5 random baseline. That was a real problem
        (a 'predictive model' with nothing to predict), fixed by making
        the synthetic cancellation probability genuinely depend on
        lead_time, price, and channel. This test locks in a band that
        would catch either failure mode: too close to 0.5 (no real
        signal) or suspiciously close to 1.0 (an unrealistic, probably
        leaky synthetic setup)."""
        result = train_cancellation_model(training_df)
        assert 0.55 <= result["test_auc"] <= 0.85

    def test_auc_stable_across_different_random_seeds(self):
        """Verifies the signal is a real property of the data-generating
        process, not a fluke of one particular train/test split."""
        aucs = []
        for seed in [1, 42, 123]:
            events = generate_raw_events(n=3000, seed=seed)
            con = new_connection()
            load_raw_events(con, events)
            run_transformations(con)
            df = build_training_frame(con)
            result = train_cancellation_model(df, random_state=seed)
            aucs.append(result["test_auc"])
        assert all(0.5 <= a <= 0.9 for a in aucs)
        # None should be suspiciously perfect.
        assert all(a < 0.95 for a in aucs)

    def test_threshold_for_target_recall_hits_approximately_that_recall(self, training_df):
        result = train_cancellation_model(training_df)
        thr = find_threshold_for_target_recall(result, target_recall=0.5)
        assert abs(thr["recall"] - 0.5) < 0.1

    def test_precision_at_threshold_beats_base_rate(self, training_df):
        """A model with real signal should give a meaningful lift over
        the base cancellation rate at a reasonable operating threshold —
        not just match it."""
        result = train_cancellation_model(training_df)
        thr = find_threshold_for_target_recall(result, target_recall=0.5)
        assert thr["precision"] > result["base_cancellation_rate"]

    def test_model_consumes_transformed_not_raw_data(self, training_df):
        """The training frame must come from fct_bookings (post-Load,
        post-Transform), not raw_events — verifying the model sits at
        the realistic point in the pipeline, after deduplication and
        product_name recovery."""
        assert training_df["product_name"].isnull().sum() == 0
        assert training_df["event_id"].duplicated().sum() == 0
