# ELT Pipeline, Self-Service Analytics & Predictive Modeling

A real, tested Python + SQL project built to close a specific gap for
Pricenow's "Working Student Data Engineering" posting: an actual ELT
pipeline (Load-then-Transform, distinct from the ETL pattern in my prior
projects), a governed self-service analytics layer, and predictive
modeling applied to pricing/booking decisions — all three named
explicitly in the posting's tasks.

## What this is (read before citing anywhere)

**There is no real Pricenow, ski-resort, or customer data here.**
`src/raw_events.py` generates synthetic booking/pricing events across a
tourism/e-commerce product set (lift passes, hotel rooms, rentals, spa
days) modeled on Pricenow's own stated domain — not real Pricenow data,
which I have no access to.

**This is genuinely ELT, not ETL relabeled.** `src/load.py` loads raw
events into a DuckDB warehouse table completely untouched — nulls,
duplicate deliveries, and inconsistent fields all included, exactly as a
real event source would deliver them. Every transformation (deduplication,
missing-value recovery via a lookup join, revenue calculation) happens
afterward as SQL running against the already-loaded table in
`src/transform.py`. This load-first, transform-in-warehouse order is the
actual architectural distinction between ELT and ETL — in ETL those
transformations would happen in an external process before loading.

## What this models

- **`src/raw_events.py`** — synthetic booking-event generator (5,000+
  events) with realistic raw-layer messiness: ~10% missing product names,
  a 2% duplicate-delivery rate, and a cancellation outcome that genuinely
  depends on lead time, price, and channel (not independent random noise
  — see "an honest finding" below).
- **`src/load.py`** — the Load stage: raw events land in DuckDB
  untouched.
- **`src/transform.py`** — the Transform stage: in-warehouse SQL
  deduplication (by exact row match, verified to NOT collapse genuinely
  distinct events that happen to share other field values) and missing-
  product-name recovery via a lookup join, producing `fct_bookings`.
- **`src/self_service.py`** — a governed self-service analytics layer:
  three named, parameterized query functions (revenue by region, channel
  performance including cancellation rate, top products by revenue) with
  validated inputs — the guardrail that makes this "self-service" rather
  than "open SQL access," since a business user's query shouldn't be able
  to hit an unbounded result set or an invalid filter silently.
- **`src/predictive_model.py`** — a cancellation-risk classifier
  (logistic regression) trained on the transformed `fct_bookings` table,
  with a business-meaningful recall-based threshold rather than an
  arbitrary 0.5 cutoff.
- **`.github/workflows/ci.yml`** — GitHub Actions CI running the full
  pipeline and test suite on every push.

## An honest finding from development

The first version of the cancellation-risk model scored an AUC of
**0.524** — barely above the 0.5 random baseline. The root cause: the
synthetic `cancelled` outcome was generated with `rng.random() < 0.08`,
completely independent of every feature. A "predictive model" with
nothing predictive in the data it was trained on isn't a real
demonstration of predictive modeling, so rather than present that number
or quietly raise it without saying why, I fixed the actual problem: the
data generator now computes cancellation probability from real,
directionally-sensible factors (longer lead time, higher price, and
call-center bookings all raise cancellation risk), with per-event random
noise layered on top so the signal is real but not perfectly separable.
After the fix, AUC settled in a genuine, modest 0.55–0.65 range across
different random seeds — verified with a dedicated test, not just
observed once. This is disclosed here rather than only in a commit
history, because presenting the original 0.524 number without
explanation would have been misleading, and presenting a fixed number
without disclosing that it needed fixing would have hidden a real,
relevant finding.

## Verification

23 tests (`pytest tests/ -v`), including:

- Load-stage tests confirming raw data (including duplicates and nulls)
  passes through completely untransformed — Load doing any cleanup would
  break the actual ELT pattern this project claims to demonstrate.
- A transform test verifying two DIFFERENT events (different event_id)
  that happen to share every other field are NOT collapsed — only true
  duplicate deliveries are, which is the correct, non-obvious dedup
  behavior.
- A revenue-calculation test cross-checking every row's
  `gross_revenue_eur` against `price * quantity` directly, not just
  trusting the SQL.
- Self-service query tests confirming invalid inputs raise a clear error
  rather than silently returning wrong or unbounded results.
- The predictive-model AUC test described above, plus a cross-seed
  stability test and a check that precision at the chosen threshold
  meaningfully beats the base cancellation rate.

## Running it

```bash
pip install -r requirements.txt
python3 -m src.pipeline    # full ELT + self-service + model run
pytest tests/ -v            # 23 tests
```

## What this doesn't demonstrate

This project doesn't use a real cloud data warehouse (BigQuery,
Snowflake, Redshift) — DuckDB runs the same ELT pattern locally, which I
disclose rather than imply otherwise — and doesn't use real Pricenow,
booking, or pricing data. It demonstrates the actual ELT architecture
(load raw, transform in-warehouse), a governed self-service query layer,
and predictive modeling with an honestly investigated and fixed signal
problem, on a system I could build, break, and verify myself.
