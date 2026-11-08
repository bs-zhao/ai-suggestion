# Original questionnaire data (restricted)

Place the two UNMODIFIED original questionnaire exports directly in this directory:

- `data1.xlsx`: 30 original responses
- `data2.xlsx`: 60 original responses

IMPORTANT: Every response in `data1.xlsx` also exists identically in `data2.xlsx`.
There are **60 unique participants**, not 90. The importer checks for exact
duplicate survey response IDs, verifies duplicate rows are identical, and
fails if any duplicate is inconsistent.

Run `python run_analysis.py --all` in the repository root. It rereads both
XLSX files and regenerates 9 analysis modules, reporting each original file's
SHA-256 fingerprint in `results/data_provenance.txt`. The original files are
read-only; the code does not edit or merge them on disk.

**Privacy:** Both original files contain potentially identifiable participant
metadata. Never upload them while the repository is Public; make it Private
first and restrict access in accordance with consent and data retention terms.
