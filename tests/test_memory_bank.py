"""Production memory: twins' memories mirrored to Vertex AI Memory Bank and recalled from it."""
from types import SimpleNamespace

import pytest

from garden import memory_bank
from garden.llm import hash_embedder
from garden.memory_bank import MemoryBankFactory, MemoryBankMemory, scope_for


class FakeBank:
    """Stands in for client.memory_banks: stores facts per scope; recall returns them in reverse order."""

    def __init__(self, fail=False):
        self.facts, self.fail = {}, fail
        self.memories = self

    def create(self, *, name, fact, scope):
        if self.fail:
            raise ConnectionError("down")
        self.facts.setdefault(tuple(scope.items()), []).append(fact)

    def retrieve(self, *, name, scope, similarity_search_params):
        if self.fail:
            raise ConnectionError("down")
        found = self.facts.get(tuple(scope.items()), [])[::-1]
        return [SimpleNamespace(memory=SimpleNamespace(fact=f)) for f in found]


def memory(bank, twin="Lina"):
    factory = MemoryBankFactory(bank=bank, bank_name="banks/1", run="r1")
    return factory(twin, hash_embedder), factory


def test_each_new_memory_is_written_once_under_the_twins_scope():
    bank = FakeBank()
    lina, factory = memory(bank)
    for text in ("Felix said hi.", "Felix said hi.", "Day 2: the court."):
        lina.add(text)
    factory.writer.shutdown(wait=True)
    assert bank.facts == {(("user_id", "garden-r1-lina"),): ["Felix said hi.", "Day 2: the court."]}


def test_recall_comes_from_memory_bank_and_falls_back_to_the_local_bank():
    bank = FakeBank()
    lina, factory = memory(bank)
    lina.extend(["Tomas loves running.", "Ravi bet on a sprint."])
    factory.writer.shutdown(wait=True)
    assert lina.retrieve_associative("running", k=1) == ["Ravi bet on a sprint."]  # the bank's answer
    down, down_factory = memory(FakeBank(fail=True))
    down.add("Tomas loves running.")
    down_factory.writer.shutdown(wait=True)
    assert down.retrieve_associative("running", k=1) == ["Tomas loves running."] and down.failures == 2


def test_scopes_keep_twins_and_runs_apart():
    assert scope_for("r1", "Ren B.") == {"user_id": "garden-r1-ren-b"}
    assert scope_for("r1", "Lina") != scope_for("r2", "Lina")


def test_memory_bank_is_off_unless_production_turns_it_on(monkeypatch):
    monkeypatch.delenv("MEMORY_BACKEND", raising=False)
    assert not memory_bank.enabled()
    monkeypatch.setenv("MEMORY_BACKEND", "memory_bank")
    assert memory_bank.enabled()
    monkeypatch.delenv("MEMORY_BANK_NAME", raising=False)
    with pytest.raises(RuntimeError):
        MemoryBankFactory(bank=FakeBank())


def test_twins_use_the_memory_they_are_given():
    from garden import Twin, WorldConfig, run_world
    from garden.concordia_twins import ConcordiaTwins
    from garden.llm import CountingModel, KeywordModel

    bank = FakeBank()
    factory = MemoryBankFactory(bank=bank, bank_name="banks/1", run="r1")
    twins = ConcordiaTwins(CountingModel(KeywordModel(), letter_choices=False), memory=factory)
    run_world(WorldConfig((Twin("Mara", "f"), Twin("Ren", "m")), max_days=1, seed=1), twins)
    factory.writer.shutdown(wait=True)
    assert {s[0][1] for s in bank.facts} == {"garden-r1-mara", "garden-r1-ren"}
