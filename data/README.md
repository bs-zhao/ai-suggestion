# Original questionnaire data (restricted)

This directory is intended to contain exactly the **unmodified original XLSX** as the analysis source of truth:

`raw/c73c62ff5ec44be1b3fc6af2d5515eb6(1).xlsx`

The original source contains identifying or potentially identifying participant information. Never commit it to a public repository. Commit it only after the GitHub repository has been confirmed Private and access limited to authorized researchers.

`python run_analysis.py --all` reads this XLSX on each run and regenerates all intermediate records and results. Nothing in the `data` folder is generated or modified by the analysis. The XLSX byte hash is recorded in `results/data_provenance.txt`.
