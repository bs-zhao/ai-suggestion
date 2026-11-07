# AI Source Labeling in Everyday Moral Advice-Taking

Reproducible analysis and publication figures for a two-arm randomized Chinese-language pilot study (60 respondents, 12 everyday dilemmas each; 720 repeated decisions). The source label is the experimental manipulation: **AI-labeled advice** vs **advice with no source specified**. Both arms received the same fixed recommendations and reasons.

## Start here

```bash
# Windows Anaconda: conda activate py11
python -m pip install -r requirements.txt

# Obtain the original workbook from the research team and KEEP IT PRIVATE.
# Run locally from the repository root (do NOT commit data_private/).
python scripts/import_raw_xlsx.py --input "PATH/TO/PRIVATE_SOURCE.xlsx" --output-dir data_private

# Reproduce all paper figures, CSV statistics, and detailed English reports.
python run_analysis.py --all

# Or run one independent module.
python run_analysis.py --module 05_conflict_source_by_switch
```

**Each module generates its own directory** under `results/<module>/`, with a detailed `results.txt`, a `statistics.csv` where appropriate, and matching 300-dpi PNG, editable SVG and vector PDF figures. Statistical results are **computed from data** on each run and are not hard-coded. You may override `--output-dir` and `--private-data-dir`.

## Output modules

| Folder | Purpose |
|---|---|
| `00_demographics/` | Age, country, primary language, AI usage, survey duration; demographics plots. |
| `01_descriptives/` | Initial agreement/conflict, overall revisions, mean pre/post confidence by source and consistency. |
| `02_conflict_adoption/` | **Result 1**: conflicting advice, source differences in adoption (participant-average Welch test, 95% CI, effect size). |
| `03_agree_no_switch_confidence/` | **Result 2**: agreeing advice **and unchanged choice**; confidence shifts within each arm and between arms. |
| `04_conflict_no_switch_confidence/` | **Result 3.1**: conflicting advice **and unchanged choice**; confidence shifts within each arm and between arms. |
| `05_conflict_source_by_switch/` | **Result 3.2**: conflicting advice, `source × whether choice was revised`, with baseline-confidence-adjusted interaction. |
| `06_scenario_heterogeneity/` | Scenario-by-scenario conflict rates and adoption; check for heterogeneous/low-denominator items. |
| `07_survey_and_quality/` | Four post-task ratings, unadjusted and Holm-adjusted p values, source recall descriptive check. |
| `08_robustness/` | Scenario-fixed-effects, respondent-clustered logistic model for adoption; exposure denominators; analytic cautions. |

Recommended main paper figures: `02`, `03`, `04`, `05`. `00` and `01` provide a demographics/overview table, while `06`–`08` are useful supplements.

## Data in this **public** repository

`data/aggregate_by_source_scenario.csv` contains only **condition-by-scenario grouped statistics** (24 rows; no respondent-level records). It permits inspection of the material and basic condition-level descriptive patterns but **cannot** reproduce individual-level hypothesis tests. All included `results/*.txt`, `statistics.csv` and SVG plots are derived aggregate outputs and carry no raw participant identifiers.

**Do not commit the raw XLSX or `data_private/`.** The original file contains participant/platform IDs, IP addresses, geographic coordinates, timestamps and optional free-text responses. The consent form describes research-only custody and does not authorize publishing individual records in a public repository. The protected local analysis input (`participants.csv`, `trials.csv`) strips direct identifiers and free text but should remain private unless a separate data-sharing authorization permits release. A private ZIP with this input is supplied separately to the study team.

`data_private/` is ignored by Git. The local importer reads the original workbook via Python's standard ZIP/XML libraries, extracts only pre-specified research variables, assigns new anonymous IDs, applies a documented column map, and validates trial encoding. It never copies IPs, platform IDs, cities, latitude/longitude, original dates, or open-ended responses to the derived CSV files. The source workbook is not modified.

## Design and statistical decisions

- `source` is determined **only by the randomized assignment column R**, not by subsequent recall of the source.
- Recommendation choices for E01–E12 are `B,A,A,A,A,B,A,B,B,B,B,A`, identical between arms. Choices are parsed as A/B. Confidence uses five ordinal categories (1=very uncertain, 5=very certain), reported as mean changes (post − pre).
- A trial is **initially conflicting** if its first choice differs from the fixed recommendation; **adoption** under conflict is when the final choice equals that recommendation. When initially agreeing, a retained original choice is **not** counted as persuasion/adoption.
- Result 1 reports (a) pooled conflict-trial adoption counts and (b) the primary mean of each participant's conflict-trial adoption proportion. These differ because participants have unequal conflict counts.
- Result 2 **excludes** the two originally agreeing trials in which the final choice changed.
- One-sample and Welch tests are run on *participant averages*, keeping the respondent as the independent unit; 95% t CIs and Hedges' g are reported. The repeated-trial interaction uses respondent-clustered robust SE, with an additional model controlling scenario and baseline confidence.
- We also show a scenario-fixed-effects respondent-clustered logistic sensitivity model for conflict adoption; it need not agree in magnitude or p-value with the participant-weighted comparison because it has different weighting and adjustment.
- Conditional analyses of choice revision (Result 3.2) are **observational after randomization** and must not be described as causal psychological reactance. Initial confidence is high, creating a potential ceiling effect. There is no no-advice arm, so pre/post changes cannot be attributed exclusively to advice presentation.
- Source-label effects are exploratory, not established just because descriptive means differ or a within-arm p-value is small. Do not claim that the unlabeled arm means human-source advice.

## Files

```text
run_analysis.py                 # Every reproducible module, deterministic random seed
scripts/import_raw_xlsx.py     # Private workbook -> deidentified local participant/trial CSVs
requirements.txt
.gitignore
data/aggregate_by_source_scenario.csv  # Public, grouped only
results/00_demographics/...    # results.txt, aggregate statistics.csv, publication figure(s)
results/01_descriptives/...
...
results/08_robustness/...
data_private/                  # Local-only, NEVER pushed to public GitHub
```

## Tests / verification

On the original provided 60-person workbook, the importer and analysis pass hard checks: 60 unique respondents, 30 per condition, 12 trials each (720 total), 241 initial-conflict trials, 61 conflict-adoption events, and all choice/confidence variable identities. The importer was compared against a separate read of the same workbook, matching every derived field. The code has been executed end-to-end; chart/report files were generated successfully.

The original data were collected in Chinese. The materials were adapted from Singer et al. (2019) but are **not** a validated 12-item EMCS short scale.
