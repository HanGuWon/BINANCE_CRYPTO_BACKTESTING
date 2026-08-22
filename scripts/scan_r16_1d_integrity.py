"""Find malformed cached 1d objects without aborting on the first issue."""
from pathlib import Path
from binance_research.data import load_kline_archive

bad = []
checked = 0
for path in sorted(Path("data/raw").glob("*/klines/*/1d/*.zip")):
    try:
        load_kline_archive(path)
        checked += 1
    except Exception as exc:
        bad.append((str(path), type(exc).__name__, str(exc)))
print({"checked": checked, "bad_count": len(bad)})
for row in bad[:20]:
    print("\t".join(row))
