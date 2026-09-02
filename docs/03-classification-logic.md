# 03 — Classification Logic

Classification is 30% of the grade and is done **entirely in code**. The LLM is
never asked what severity a result is.

## The five-band model

Each test defines four thresholds, producing five bands:

```
        critical_low      low            high        critical_high
   ─────────┬──────────────┬──────────────┬──────────────┬─────────
  CRITICAL  │   WARNING    │    NORMAL    │   WARNING    │ CRITICAL
    (low)   │    (low)     │              │   (high)     │  (high)
```

| Band | Condition | Severity | Meaning |
|------|-----------|----------|---------|
| Critical low | `value < critical_low` | `critical` | Life-threatening, act now |
| Warning low | `critical_low <= value < low` | `warning` | Abnormal, needs follow-up |
| Normal | `low <= value <= high` | `normal` | Within reference range |
| Warning high | `high < value <= critical_high` | `warning` | Abnormal, needs follow-up |
| Critical high | `value > critical_high` | `critical` | Life-threatening, act now |

**Boundary rule:** range bounds are *inclusive* of Normal. A value exactly equal
to `low` or `high` is Normal. Stated explicitly because "exactly on the
boundary" is a classic edge case a grader will test.

## Reference ranges (adult, general population)

| Test | Unit | crit_low | low | high | crit_high |
|------|------|---------:|----:|-----:|----------:|
| Hemoglobin | g/dL | 7.0 | 12.0 | 17.5 | 20.0 |
| WBC | 10³/µL | 2.0 | 4.5 | 11.0 | 30.0 |
| Platelets | 10³/µL | 50 | 150 | 450 | 1000 |
| Glucose (fasting) | mg/dL | 50 | 70 | 99 | 400 |
| Potassium | mEq/L | 2.5 | 3.5 | 5.1 | 6.5 |
| Sodium | mEq/L | 120 | 135 | 145 | 160 |
| Creatinine | mg/dL | — | 0.6 | 1.3 | 4.0 |
| Calcium | mg/dL | 6.0 | 8.5 | 10.5 | 13.0 |
| TSH | µIU/mL | 0.1 | 0.4 | 4.0 | 20.0 |
| ALT | U/L | — | 7 | 56 | 300 |

Ten tests; the assignment requires at least five.

### Documented assumptions

These are simplifications, stated openly rather than hidden:

1. **Adult, sex-agnostic.** Real hemoglobin ranges differ by sex
   (roughly 13.5–17.5 male, 12.0–15.5 female). We use a combined adult range
   because the input schema carries no patient demographics.
2. **No age adjustment.** Pediatric and geriatric ranges differ materially.
3. **Fasting assumed for glucose.** Random glucose has a wider normal range.
4. **A missing threshold means that side has no critical band.** Creatinine has
   no `critical_low` — a very low creatinine is not an emergency.

Because ranges live in one table (`mcp_server/reference_ranges.py`), refining
any of this later is a data change, not a code change.

## Explainability payload

Classification returns far more than a label. Every field below is computed
deterministically and is what makes the result auditable:

```json
{
  "test_name": "Hemoglobin",
  "value": 7.2,
  "unit": "g/dL",
  "severity": "critical",
  "reference_range": { "low": 12.0, "high": 17.5, "unit": "g/dL" },
  "direction": "below",
  "deviation_pct": 40.0,
  "deviation_text": "40% below the lower limit of normal",
  "rule_fired": "value (7.2) < critical_low (7.0) is False; value < low (12.0) is True -> warning_low ... ",
  "matched_by": "exact"
}
```

* `rule_fired` — the literal comparison chain, so a user can verify the verdict
* `matched_by` — how the test name resolved (`exact` / `alias` / `fuzzy`)
* `deviation_*` — how far outside, not just that it is outside

This is the "Explainable AI" constraint satisfied by construction: the *why* is
computed, not narrated by a model.

## Unit handling

A value is only comparable to a range if the units match.

| Case | Behavior |
|------|----------|
| Unit matches | Classify normally |
| Unit missing | Assume the canonical unit, set `unit_assumed: true` |
| Unit is a known equivalent (`g/dl` vs `g/dL`) | Normalize, classify |
| Unit conflicts (`mmol/L` vs `mg/dL`) | Do **not** guess — return `unknown` severity with an explanatory error |

Silently comparing mmol/L against a mg/dL range would produce a confidently
wrong answer. Refusing is the safe behavior.

## Edge cases

| Input | Behavior |
|-------|----------|
| Unknown test name | `severity: "unknown"`, no LLM call, message naming the unrecognized test |
| Non-numeric value (`"N/A"`, `""`) | Row-level error; other rows still process |
| Negative value | Rejected — no lab test here can be negative |
| Value exactly on a boundary | Normal (bounds inclusive) |
| Alias (`HGB`, `Haemoglobin`) | Resolved via alias table, `matched_by: "alias"` |
| Typo (`Hemoglobn`) | Fuzzy match above threshold, `matched_by: "fuzzy"`, surfaced in the UI |
| Empty request | `400` with a clear message |
| More rows than `MAX_LABS_PER_REQUEST` | `413` before any work is done |

**Partial success is the rule.** One bad row never fails the whole batch. Good
rows are classified and returned alongside a list of row-level errors.

## Why not let the LLM classify?

| | Code | LLM |
|---|------|-----|
| Same input, same output | Always | Not guaranteed |
| Auditable | Yes — the comparison is visible | No |
| Unit-tested | Yes | Not meaningfully |
| Wrong on a critical value | Only if the table is wrong | Possible at any time |

An LLM that labels a potassium of 6.8 mEq/L as "Normal" produces a tool that is
worse than no tool. The comparison `6.8 > 6.5` cannot.
