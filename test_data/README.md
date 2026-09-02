# Test Data

Three synthetic CSVs covering distinct scenarios (assignment deliverable).
Synthetic by design — no real patient data.

| File | Scenario | Purpose |
|------|----------|---------|
| `normal_panel.csv` | All values within reference ranges | Happy path; confirms normals still get LLM explanations |
| `critical_panel.csv` | Several life-threatening values | Exercises critical routing and ordering |
| `mixed_messy_panel.csv` | Mixed severities plus deliberately bad rows | Exercises error handling: unknown tests, blank values, aliases, typos, boundary values |

Format:

```csv
test_name,value,unit
Hemoglobin,7.2,g/dL
```

Column aliases are tolerated — see [API contract](../docs/04-api-contract.md).
