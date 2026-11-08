# AI Source Labeling in Everyday Moral Advice-Taking

Reproducible analysis and publication figures for a two-arm randomized Chinese-language pilot study (60 respondents, 12 everyday dilemmas each; 720 repeated decisions). The source label is the experimental manipulation: **AI-labeled advice** vs **advice with no source specified**. Both arms received the same fixed recommendations and reasons.

## Reproducible pipeline — from the exact original Excel

**Data confidentiality: this repository MUST be private before committing the source workbooks.**
The two untouched original exports belong directly under `data/`:
`data/data1.xlsx` (30 responses) and `data/data2.xlsx` (60 responses).
**All 30 data1 records also occur identically in data2; the unique N is 60, NOT 90.**
The importer cross-checks exact duplicates by original response ID and refuses conflicting records.

```bat
conda activate py11
python -m pip install -r requirements.txt
python run_analysis.py --all
```

To run only the source-by-choice-revision analysis (still imports both original XLSX files first):

```bat
python run_analysis.py --module 05_conflict_source_by_switch
```

To override the two source paths, pass the original Excel paths as repeated arguments:

```bat
python run_analysis.py --all --raw-xlsx "D:\Research\data1.xlsx" --raw-xlsx "D:\Research\data2.xlsx"
```

**Every run starts by parsing both original workbooks.** There is no fallback to
cached `participants.csv`/`trials.csv`: the importer re-creates both files in
`data_private/` on every invocation, validates duplicate overlap and 60 participants, two groups
of 30, and 720 trials. It records the SHA-256 fingerprint of each original workbook
in `results/data_provenance.txt` and each module's `data_provenance.txt`.
Both raw inputs are read-only; original records are never changed.

Outputs are in `results/<module>/`, containing a detailed `results.txt`,
`statistics.csv` (where applicable), and matching publication figures as
300-dpi PNG, editable SVG and vector PDF. Use `--output-dir` to change output.

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

## Data protection and source of truth

This study's original workbooks include direct and indirect personal identifiers
such as platform IDs, IP addresses, geography, response times and free text.
Although stored in `data/` for the private research project, **do not change
the repository to public while either original workbook is included**. Git commits
and their history may retain past versions of sensitive files even after deletion.
Access must be restricted to authorized researchers and applicable consent terms.

Both original XLSX files are retained byte-for-byte and analyzed only once per distinct response ID. Derived
`data_private/participants.csv` and `data_private/trials.csv` are **temporary,
regenerated intermediates**; do not use them as canonical data, and do not
commit them. The importer discards identifiers and free text from derived CSVs.
No preprocessed data are committed under `data/`. All descriptive statistics are regenerated under `results/`.

The repository initially originated as a *public* code-only repository. The two raw
files must be added to GitHub **only after** verifying repository visibility is
Private. The downloadable full local package includes the original raw file
and is designed to be committed once the repository has been secured.

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
scripts/import_raw_xlsx.py     # Original Excel -> deidentified intermediate CSVs
requirements.txt
.gitignore
data/data1.xlsx               # Original 30 responses; subset of data2, PRIVATE ONLY
data/data2.xlsx               # Original 60 responses, PRIVATE ONLY
results/00_demographics/...    # results.txt, aggregate statistics.csv, publication figure(s)
results/01_descriptives/...
...
results/08_robustness/...
data_private/                  # Generated intermediates, ignored by Git
```

## Tests / verification

When run on both original supplied workbooks (30 and 60 responses, exact 30-response overlap), the importer and analysis verify: 60 unique respondents, 30 per condition, 12 trials each (720 total), 241 initial-conflict trials, 61 conflict-adoption events, and all choice/confidence variable identities. The importer was compared against a separate read of the same workbook, matching every derived field. The code has been executed end-to-end; chart/report files were generated successfully.

The original data were collected in Chinese. The materials were adapted from Singer et al. (2019) but are **not** a validated 12-item EMCS short scale.
