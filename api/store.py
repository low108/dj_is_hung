"""Where simulation records live: Firestore (emulator or cloud) or memory for tests."""
from __future__ import annotations

import os
from typing import Protocol


class SimulationStore(Protocol):
    def save(self, sim_id: str, record: dict) -> None: ...
    def get(self, sim_id: str) -> dict | None: ...


class MemoryStore:
    def __init__(self):
        self._records: dict[str, dict] = {}

    def save(self, sim_id: str, record: dict) -> None:
        self._records[sim_id] = record

    def get(self, sim_id: str) -> dict | None:
        return self._records.get(sim_id)


class FirestoreStore:
    def __init__(self, project: str):
        from google.cloud import firestore

        self._col = firestore.Client(project=project).collection("simulations")

    def save(self, sim_id: str, record: dict) -> None:
        self._col.document(sim_id).set(record)

    def get(self, sim_id: str) -> dict | None:
        snap = self._col.document(sim_id).get()
        return snap.to_dict() if snap.exists else None


def default_store() -> SimulationStore:
    """Firestore when an emulator or project is configured, otherwise memory."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if os.environ.get("FIRESTORE_EMULATOR_HOST") or project:
        return FirestoreStore(project or "demo-dj-is-hung")
    return MemoryStore()
