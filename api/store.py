"""Where the API keeps its data: Firestore (emulator or cloud) or memory for tests."""
from __future__ import annotations

import copy
import os
import threading
from collections.abc import Callable
from typing import Protocol


class Store(Protocol):
    """Simulations (with their events and twin snapshots) and users (onboarding, D3)."""

    def save(self, sim_id: str, record: dict) -> None: ...
    def get(self, sim_id: str) -> dict | None: ...
    def add_events(self, sim_id: str, events: list[dict]) -> None: ...
    def events(self, sim_id: str, after: int = -1) -> list[dict]: ...
    def save_twin_states(self, sim_id: str, states: list[dict]) -> None: ...
    def twin_states(self, sim_id: str) -> list[dict]: ...
    def get_user(self, uid: str) -> dict | None: ...
    def update_user(self, uid: str, change: Callable[[dict | None], dict]) -> dict:
        """Atomically replace the user's document with change(current) and return it. If `change`
        raises, nothing is written."""
        ...


class MemoryStore:
    def __init__(self):
        self._records: dict[str, dict] = {}
        self._events: dict[str, list[dict]] = {}
        self._twins: dict[str, list[dict]] = {}
        self._users: dict[str, dict] = {}
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

    def get_user(self, uid: str) -> dict | None:
        with self._lock:
            doc = self._users.get(uid)
            return copy.deepcopy(doc) if doc is not None else None

    def update_user(self, uid: str, change: Callable[[dict | None], dict]) -> dict:
        with self._lock:
            current = self._users.get(uid)
            doc = change(copy.deepcopy(current) if current is not None else None)
            self._users[uid] = copy.deepcopy(doc)
            return copy.deepcopy(doc)


class FirestoreStore:
    def __init__(self, project: str):
        from google.cloud import firestore

        self._db = firestore.Client(project=project)
        self._col = self._db.collection("simulations")
        self._users = self._db.collection("users")

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

    def get_user(self, uid: str) -> dict | None:
        snap = self._users.document(uid).get()
        return snap.to_dict() if snap.exists else None

    def update_user(self, uid: str, change: Callable[[dict | None], dict]) -> dict:
        from google.cloud import firestore

        ref = self._users.document(uid)

        @firestore.transactional
        def run(transaction) -> dict:
            snap = ref.get(transaction=transaction)
            doc = change(snap.to_dict() if snap.exists else None)
            transaction.set(ref, doc)
            return doc

        return run(self._db.transaction())


def default_store() -> Store:
    """Firestore when an emulator or project is configured, otherwise memory."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if os.environ.get("FIRESTORE_EMULATOR_HOST") or project:
        return FirestoreStore(project or "demo-dj-is-hung")
    return MemoryStore()
