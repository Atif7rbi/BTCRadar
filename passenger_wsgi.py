from pathlib import Path
import sys

SNIPER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SNIPER_ROOT / "deploy"))

from passenger_loader import launch_project

application = launch_project("btcradar")