# Contributing

Use a focused branch and keep generated corpora, solver binaries, LaTeX
auxiliaries, credentials, and machine-specific paths out of commits.

Before opening a pull request, run:

```bash
python3 -m pytest -q
python3 -m compileall -q code tests
python3 code/quality/verify_corpora.py --data-root datasets
python3 code/quality/build_manifest.py --check
```

Heavy solver or training changes require a SLURM job-scoped result containing
the source commit, input and executable hashes, environment, fixed split/seeds,
raw measurements, and declared tolerance. Manuscript claims must be generated
from those records rather than copied manually.
