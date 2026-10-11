"""Where simulation records live: Firestore (emulator or cloud) or memory for tests."""
from __future__ import annotations

import os
import threading
from typing import Protocol


class SimulationStore(Protocol):
    def save(self, sim_id: str, record: dict) -> None: ...
    def get(self, sim_id: str) -> dict | None: ...
    def add_events(self, sim_id: str, events: list[dict]) -> None: ...
    def events(self, sim_id: str, after: int = -1) -> list[dict]: ...
    def save_twin_states(self, sim_id: str, states: list[dict]) -> None: ...
    def twin_states(self, sim_id: str) -> list[dict]: ...


class MemoryStore:
    def __init__(self):
        self._records: dict[str, dict] = {}
        self._events: dict[str, list[dict]] = {}
        self._twins: dict[str, list[dict]] = {}
        self._lock = threading.Lock()  # the simulation thread writes while requests read

    def save(self, sim_id: str, record: dict) -> None:
        with self._lock:
            self._records[sim_id] = dict(record)

    def get(self, sim_id: str) -> dict | None:
        with self._lock:
            record = self._records.get(sim_id)
            return dict(record) if record is not None else None

    def add_events(self, sim_id: str, events: list[dict]) -> None:
        with self._lock:
            self._events.setdefault(sim_id, []).extend(events)

    def events(self, sim_id: str, after: int = -1) -> list[dict]:
        with self._lock:
            return [e for e in self._events.get(sim_id, []) if e["seq"] > after]

    def save_twin_states(self, sim_id: str, states: list[dict]) -> None:
        with self._lock:
            self._twins.setdefault(sim_id, []).extend(states)

    def twin_states(self, sim_id: str) -> list[dict]:
        with self._lock:
            return list(self._twins.get(sim_id, []))


class FirestoreStore:
    def __init__(self, project: str):
        from google.cloud import firestore

        self._db = firestore.Client(project=project)
        self._col = self._db.collection("simulations")

    def save(self, sim_id: str, record: dict) -> None:
        self._col.document(sim_id).set(record)

    def get(self, sim_id: str) -> dict | None:
        snap = self._col.document(sim_id).get()
        return snap.to_dict() if snap.exists else None

    def add_events(self, sim_id: str, events: list[dict]) -> None:
        batch = self._db.batch()
        sub = self._col.document(sim_id).collection("events")
        for e in events:
            batch.set(sub.document(f"{e['seq']:06d}"), e)
        batch.commit()

    def events(self, sim_id: str, after: int = -1) -> list[dict]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        sub = self._col.document(sim_id).collection("events")
        return [d.to_dict() for d in sub.where(filter=FieldFilter("seq", ">", after)).order_by("seq").stream()]

    def save_twin_states(self, sim_id: str, states: list[dict]) -> None:
        batch = self._db.batch()
        sub = self._col.document(sim_id).collection("twins")
        for state in states:  # one document per twin per evening, so the viewer can follow the map's day
            batch.set(sub.document(f"{state['day']:03d}-{state['twin']}"), state)
        batch.commit()

    def twin_states(self, sim_id: str) -> list[dict]:
        return [d.to_dict() for d in self._col.document(sim_id).collection("twins").stream()]


def default_store() -> SimulationStore:
    """Firestore when an emulator or project is configured, otherwise memory."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if os.environ.get("FIRESTORE_EMULATOR_HOST") or project:
        return FirestoreStore(project or "demo-dj-is-hung")
    return MemoryStore()
