"""Production twin memory: Vertex AI Memory Bank (Google Cloud Agent Platform), behind Concordia's memory.

Each twin's memories still live in Concordia's local bank (recency, scans and saved state work as
before) and are also written to Memory Bank as facts, scoped to that twin in that run. Recall by meaning
("what does Lina remember about the court?") goes to Memory Bank's similarity search, which embeds with
Google's text-embedding model; if Memory Bank can't be reached the twin falls back to its local bank, so
an outage never ends a run. Writes go out in the background so a run doesn't wait on them.

Only for production: switched on with MEMORY_BACKEND=memory_bank (development keeps the free local bank).
Memory Bank is billed per event (Sessions and Memory Bank: about $0.25 per 1,000 events).

    MEMORY_BACKEND=memory_bank
    MEMORY_BANK_NAME=projects/.../locations/.../memoryBanks/...   # from scripts/create_memory_bank.py
    VERTEX_API_KEY=...            # Vertex AI express mode; or, instead,
    GOOGLE_CLOUD_PROJECT=...      # a project with your Google Cloud login (ADC) and
    GOOGLE_CLOUD_LOCATION=us-central1
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from concordia.associative_memory import basic_associative_memory

log = logging.getLogger(__name__)

BACKEND_ENV = "MEMORY_BACKEND"
WRITERS = 4  # background writes in flight per process


def enabled() -> bool:
    return os.environ.get(BACKEND_ENV, "local").strip().lower() == "memory_bank"


def client():
    """An Agent Platform client: express mode with VERTEX_API_KEY, else the project with Google Cloud login."""
    import agentplatform

    key = os.environ.get("VERTEX_API_KEY")
    if key:
        return agentplatform.Client(api_key=key)
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise RuntimeError("Memory Bank needs VERTEX_API_KEY (express mode) or GOOGLE_CLOUD_PROJECT")
    return agentplatform.Client(project=project, location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"))


def scope_for(run: str, twin: str) -> dict[str, str]:
    """Whose memories these are: one twin in one run (twins of different runs never share memories)."""
    return {"user_id": re.sub(r"[^a-z0-9-]+", "-", f"garden-{run}-{twin}".lower()).strip("-")}


class MemoryBankMemory(basic_associative_memory.AssociativeMemoryBank):
    """Concordia's memory bank, mirrored to Vertex AI Memory Bank and recalled by its similarity search."""

    def __init__(self, bank, bank_name: str, scope: dict[str, str], sentence_embedder: Callable[[str], np.ndarray],
                 writer: ThreadPoolExecutor | None = None):
        super().__init__(sentence_embedder=sentence_embedder)
        self._bank = bank  # an agentplatform client's memory_banks
        self._name = bank_name
        self._scope = scope
        self._writer = writer or ThreadPoolExecutor(max_workers=1)
        self.failures = 0  # Memory Bank calls that failed (the local bank answered instead)

    def add(self, text: str) -> None:
        before = len(self._stored_hashes)
        super().add(text)
        if len(self._stored_hashes) > before:  # new to this twin (Concordia skips duplicates)
            self._writer.submit(self._write, text.replace("\n", " "))

    def _write(self, fact: str) -> None:
        try:
            self._bank.memories.create(name=self._name, fact=fact, scope=self._scope)
        except Exception as e:  # a lost write only costs recall quality; the local bank still has it
            self.failures += 1
            log.warning("Memory Bank write failed (%s): %s", type(e).__name__, e)

    def retrieve_associative(self, query: str, k: int = 1) -> Sequence[str]:
        try:
            found = self._bank.memories.retrieve(name=self._name, scope=self._scope,
                                                 similarity_search_params={"search_query": query, "top_k": k})
            facts = [m.memory.fact for m in found if m.memory and m.memory.fact]
            if facts:
                return facts[:k]
        except Exception as e:
            self.failures += 1
            log.warning("Memory Bank recall failed (%s): %s", type(e).__name__, e)
        return super().retrieve_associative(query, k)  # not written yet, or unreachable: the local bank


class MemoryBankFactory:
    """Makes each twin's memory for one run. `bank` and `writer` are shared by every twin in the run."""

    def __init__(self, bank=None, bank_name: str | None = None, run: str | None = None):
        self.bank_name = bank_name or os.environ.get("MEMORY_BANK_NAME", "")
        if not self.bank_name:
            raise RuntimeError("MEMORY_BANK_NAME is not set: create one with scripts/create_memory_bank.py")
        self.bank = bank if bank is not None else client().memory_banks
        self.run = run or uuid.uuid4().hex[:12]
        self.writer = ThreadPoolExecutor(max_workers=WRITERS)

    def __call__(self, twin: str, sentence_embedder: Callable[[str], np.ndarray]) -> MemoryBankMemory:
        return MemoryBankMemory(self.bank, self.bank_name, scope_for(self.run, twin), sentence_embedder, self.writer)
