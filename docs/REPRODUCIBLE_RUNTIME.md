# Reproducible runtime contract

The research package supports Python 3.11 or newer. Install the declared
development dependencies from the repository root with:

```text
python -m pip install -e ".[dev]"
```

The canonical test invocation is:

```text
python -m pytest -q tests ops/r3/tests -p no:cacheprovider
```

The package resolves default configuration and raw/forward collection paths
from the repository root, not from the caller's current working directory.
Explicit `--config`, `--raw-root`, and `--output` arguments remain authoritative.
The runtime contract does not include virtual environments, caches, raw
archives, Parquet data, or generated research outcomes in Git.
