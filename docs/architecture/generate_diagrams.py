"""Export Coductor architecture HTML diagrams to PNG."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPORTED = ROOT / "exported"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

DIAGRAMS = {
    "coductor-system-overview.html": "coductor-system-overview.png",
    "coductor-runtime-flow.html": "coductor-runtime-flow.png",
    "coductor-artifact-state-flow.html": "coductor-artifact-state-flow.png",
}


def export_pngs() -> None:
    if not CHROME.exists():
        raise RuntimeError(f"Chrome not found at {CHROME}")
    EXPORTED.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="coductor-chrome-profile-") as profile:
        for source, target in DIAGRAMS.items():
            html_path = ROOT / source
            png_path = EXPORTED / target
            command = [
                str(CHROME),
                "--headless=new",
                "--disable-gpu",
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-default-apps",
                "--disable-sync",
                "--hide-scrollbars",
                "--no-first-run",
                "--no-default-browser-check",
                f"--user-data-dir={profile}",
                "--force-device-scale-factor=2",
                "--window-size=1800,1100",
                f"--screenshot={png_path}",
                html_path.resolve().as_uri(),
            ]
            try:
                subprocess.run(
                    command,
                    timeout=15,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.TimeoutExpired as exc:
                if png_path.exists():
                    continue
                raise RuntimeError(f"Chrome export timed out for {source}") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--export-png",
        action="store_true",
        help="export HTML diagram sources to PNG",
    )
    args = parser.parse_args()
    if args.export_png:
        export_pngs()


if __name__ == "__main__":
    main()
