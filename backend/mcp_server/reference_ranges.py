"""Clinical reference range table — the single source of truth.

Each test defines four thresholds that produce five severity bands:

    critical_low   low        high        critical_high
    ────┬──────────┬──────────┬───────────┬────────
   CRIT │ WARNING  │  NORMAL  │  WARNING  │  CRIT

Ranges are adult-general and documented with their source in docs/.

TODO(step 2): REFERENCE_RANGES dict + unit metadata + aliases.
"""
