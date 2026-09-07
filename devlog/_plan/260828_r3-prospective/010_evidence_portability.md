# Evidence portability implementation

Use `scripts/evidence_paths.py` only for the preserved v6 regression audit.
The resolver checks both native Windows and `/mnt/<drive>` WSL mappings, then
requires the expected R2B campaign, 576 units, frozen registry SHA, and
`UNTOUCHED` holdout status. It returns `None` with an explicit skip reason
when that immutable evidence is unavailable; arbitrary manifest-bearing paths
are rejected.

`scripts/portable_semantic_hash.py` adds an optional audit representation for
CSV/JSON. Canonical files remain byte-immutable. Supplemental metadata records
both canonical file SHA256 and normalized semantic SHA256, with LF encoding,
stable rows/keys, deterministic numeric/NaN text, and non-scientific path
normalization.
