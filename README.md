# ELT Pipeline, Self-Service Analytics & Predictive Modeling

A tested Python + SQL project with three parts: an ELT pipeline
(Load-then-Transform, distinct from the ETL pattern in my earlier
projects), a governed self-service analytics layer, and predictive
modeling applied to pricing/booking decisions.

## What it does

- **`src/raw_events.py`** — synthetic booking-event generator (5,000+
  events) with realistic raw-layer messiness: ~10% missing product names,
  a 2% duplicate-delivery rate, and a cancellation outcome that depends on
  lead time, price, and channel (see Results).
- **`src/load.py`** — the Load stage: raw events land in a DuckDB
  warehouse table completely untouched, with nulls, duplicate deliveries,
  and inconsistent fields all included, exactly as a real event source
  would deliver them.
- **`src/transform.py`** — the Transform stage: in-warehouse SQL
  deduplication (by exact row match, verified to NOT collapse genuinely
  distinct events that happen to share other field values) and
  missing-product-name recovery via a lookup join, producing
  `fct_bookings`. Every transformation runs as SQL against the
  already-loaded table; this load-first, transform-in-warehouse order is
  the architectural distinction between ELT and ETL, where those
  transformations would happen in an external process before loading.
- **`src/self_service.py`** — a governed self-service analytics layer:
  three named, parameterized query functions (revenue by region, channel
  performance including cancellation rate, top products by revenue) with
  validated inputs. The guardrails are what make this "self-service"
  rather than "open SQL access," since a business user's query shouldn't
  be able to hit an unbounded result set or an invalid filter silently.
- **`src/predictive_model.py`** — a cancellation-risk classifier (logistic
  regression) trained on the transformed `fct_bookings` table, with a
  business-meaningful recall-based threshold rather than an arbitrary 0.5
  cutoff.
- **`.github/workflows/ci.yml`** — GitHub Actions CI running the full
  pipeline and test suite on every push.

## Data

The data is synthetic. `src/raw_events.py` generates booking/pricing
events across a tourism/e-commerce product set (lift passes, hotel rooms,
rentals, spa days). DuckDB runs the ELT pattern locally in place of a
cloud data warehouse (BigQuery, Snowflake, Redshift); the same
load-then-transform SQL carries over.

## Results

My first version of the cancellation-risk model scored an AUC of
**0.524**, barely above the 0.5 random baseline. The cause was in the
synthetic data: the `cancelled` outcome was generated with
`rng.random() < 0.08`, independent of every feature. I fixed the
generator so cancellation probability is computed from directionally
sensible factors (longer lead time, higher price, and call-center
bookings all raise cancellation risk), with per-event random noise layered
on top so the signal is real but not perfectly separable. After the fix,
AUC settled in a modest 0.55–0.65 range across different random seeds,
verified with a dedicated test.

## Tests

23 tests (`pytest tests/ -v`), including:

- Load-stage tests confirming raw data (including duplicates and nulls)
  passes through completely untransformed, which keeps the ELT pattern
  intact.
- A transform test verifying two DIFFERENT events (different event_id)
  that share every other field are NOT collapsed; only true duplicate
  deliveries are.
- A revenue-calculation test cross-checking every row's
  `gross_revenue_eur` against `price * quantity` directly.
- Self-service query tests confirming invalid inputs raise a clear error
  rather than silently returning wrong or unbounded results.
- The predictive-model AUC test described above, a cross-seed stability
  test, and a check that precision at the chosen threshold meaningfully
  beats the base cancellation rate.

## Running it

```bash
pip install -r requirements.txt
python3 -m src.pipeline    # full ELT + self-service + model run
pytest tests/ -v            # 23 tests
```

## Possible extensions

- Point the Load stage at a cloud warehouse (BigQuery, Snowflake,
  Redshift) instead of local DuckDB.
- Swap the synthetic event generator for a real booking/pricing event
  feed.
