from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.collectors.okx_provider import OKXProvider, OKX_SYMBOLS


def main() -> int:
    provider = OKXProvider(timeout=10, period="5m")

    for symbol in OKX_SYMBOLS:
        snap = provider.get_ls_snapshot(symbol)

        print(f"\n{symbol}")
        for label, value in [
            ("LS_RATIO", snap.ls_ratio),
            ("LS_ACCOUNT", snap.ls_account),
            ("LS_POSIT", snap.ls_posit),
        ]:
            print(
                f"{label:<10} "
                f"ratio={value.ratio:.4f} "
                f"long={value.long_pct:.2f}% "
                f"short={value.short_pct:.2f}% "
                f"ts={value.ts_ms}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
