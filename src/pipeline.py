"""
End-to-end ELT + self-service + predictive-modeling runner.
"""

from src.raw_events import generate_raw_events
from src.load import new_connection, load_raw_events
from src.transform import run_transformations
from src.self_service import revenue_by_region, channel_performance, top_products_by_revenue
from src.predictive_model import build_training_frame, train_cancellation_model, find_threshold_for_target_recall


def run():
    print("=" * 70)
    print("EXTRACT/LOAD")
    print("=" * 70)
    events = generate_raw_events(n=5000, seed=17)
    con = new_connection()
    loaded = load_raw_events(con, events)
    print(f"Loaded {loaded} raw events (untransformed) into raw_events.")

    print("\n" + "=" * 70)
    print("TRANSFORM (in-warehouse SQL)")
    print("=" * 70)
    report = run_transformations(con)
    for k, v in report.items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 70)
    print("SELF-SERVICE ANALYTICS LAYER")
    print("=" * 70)
    print("\nRevenue by region:")
    print(revenue_by_region(con).to_string(index=False))
    print("\nChannel performance:")
    print(channel_performance(con).to_string(index=False))
    print("\nTop 3 products by revenue:")
    print(top_products_by_revenue(con, limit=3).to_string(index=False))

    print("\n" + "=" * 70)
    print("PREDICTIVE MODEL — cancellation risk")
    print("=" * 70)
    df = build_training_frame(con)
    result = train_cancellation_model(df)
    print(f"Base cancellation rate: {result['base_cancellation_rate']:.1%}")
    print(f"Held-out test AUC: {result['test_auc']:.3f}")
    thr = find_threshold_for_target_recall(result, target_recall=0.5)
    print(f"Threshold for ~50% recall: precision={thr['precision']:.1%} "
          f"recall={thr['recall']:.1%} (base rate {result['base_cancellation_rate']:.1%})")


if __name__ == "__main__":
    run()
