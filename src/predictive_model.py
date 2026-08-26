"""
Predictive modeling on the transformed booking data: a cancellation-risk
classifier — the posting's "predictive modelling to optimise customer
decisions and pricing strategies" task, applied concretely. Knowing which
bookings are at elevated cancellation risk lets a pricing/ops team target
confirmation nudges or adjust overbooking assumptions, similar in shape
to the no-show risk model built for a prior application, applied here to
Pricenow's actual domain (pricing/e-commerce/tourism) instead.

Uses only the transformed fct_bookings table — the model consumes
ELT-transformed data, not raw events, which is the realistic point in a
pipeline where a predictive model would actually sit.
"""

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, precision_recall_curve
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


FEATURE_COLUMNS = ["category", "channel", "region", "lead_time_days", "booked_price_eur", "quantity"]
CATEGORICAL_COLUMNS = ["category", "channel", "region"]
NUMERIC_COLUMNS = ["lead_time_days", "booked_price_eur", "quantity"]


def build_training_frame(con):
    df = con.execute("SELECT * FROM fct_bookings").fetchdf()
    return df


def train_cancellation_model(df, random_state=42):
    X = df[FEATURE_COLUMNS]
    y = df["cancelled"].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=random_state, stratify=y
    )

    preprocessor = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_COLUMNS),
    ], remainder="passthrough")

    pipeline = Pipeline([
        ("preprocess", preprocessor),
        ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])
    pipeline.fit(X_train, y_train)

    y_proba = pipeline.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_proba)

    precision, recall, thresholds = precision_recall_curve(y_test, y_proba)

    return {
        "pipeline": pipeline,
        "test_auc": auc,
        "y_test": y_test,
        "y_proba": y_proba,
        "precision_curve": precision,
        "recall_curve": recall,
        "thresholds": thresholds,
        "base_cancellation_rate": float(y.mean()),
    }


def find_threshold_for_target_recall(result, target_recall=0.5):
    """Finds a probability threshold hitting approximately the target
    recall — the same 'pick a threshold that hits a business-meaningful
    recall, not an arbitrary 0.5 cutoff' pattern used in prior work."""
    precision, recall, thresholds = (
        result["precision_curve"], result["recall_curve"], result["thresholds"]
    )
    # precision_recall_curve returns one more precision/recall point than
    # thresholds; align by dropping the last precision/recall point.
    best_idx = None
    best_diff = float("inf")
    for i, r in enumerate(recall[:-1]):
        diff = abs(r - target_recall)
        if diff < best_diff:
            best_diff = diff
            best_idx = i
    return {
        "threshold": float(thresholds[best_idx]),
        "precision": float(precision[best_idx]),
        "recall": float(recall[best_idx]),
    }
