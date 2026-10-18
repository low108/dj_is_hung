"""Create the production Memory Bank once and print its name for MEMORY_BANK_NAME.

    uv run --env-file .env python scripts/create_memory_bank.py

Uses VERTEX_API_KEY (Vertex AI express mode) or GOOGLE_CLOUD_PROJECT with your Google Cloud login.
The bank uses Google's defaults (Gemini Flash to consolidate, text-embedding-005 for similarity search).
Memory Bank is billed per event; creating the bank itself stores nothing yet.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from garden import memory_bank  # noqa: E402

bank = memory_bank.client().memory_banks.create()
print(f"MEMORY_BANK_NAME={bank.name}")
