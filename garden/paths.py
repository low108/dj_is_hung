"""Where local data lives (the dataset, run logs, prompt versions)."""
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
