# Public group-level data only

`aggregate_by_source_scenario.csv` is derived from the full 60-person study but is aggregated by study arm and question (2 × 12 rows). `n_conflict_adopt` counts revised choices after initially conflicting advice; other statistics are descriptives.

There are deliberately no participant IDs, IPs, dates, geographical coordinates, personal free-text responses or trial-level records in this public folder. To re-run hypothesis tests, use the separately delivered private deidentified CSVs in `data_private/` on a local machine, or run `scripts/import_raw_xlsx.py` with the study's original workbook stored outside Git.

Interpretation: `AI_label` indicates the randomized group explicitly shown an AI label; `Unlabeled` indicates **no source specified**, not an explicit human advisor.
