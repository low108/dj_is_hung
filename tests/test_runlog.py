"""F1: run logging (local JSON lines, BigQuery-shaped) and prompt versioning."""
import json

from garden import demo, prompts
from garden.batch import PriceLevel, plan, run_simulation
from garden.runlog import write_simulation

RUN_FIELDS = {"seed", "prompt_version", "model", "temperature", "price_level", "outcome", "breakout_pair", "day_ended"}


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def simulate(tmp_path):
    specs = plan(["fake:a", "fake:b"], list(PriceLevel), [0])
    sim = run_simulation(specs, demo.POOL, demo.make_twin_model, max_days=5)
    return write_simulation("sim-test", sim, demo.WOMAN, demo.MEN, out_dir=tmp_path / "runs",
                            prompts_dir=tmp_path / "prompts"), sim


def test_all_four_tables_get_rows_for_every_run(tmp_path):
    directory, sim = simulate(tmp_path)
    run_ids = {r.spec.run_id for r in sim.records}
    assert {r["run_id"] for r in rows(directory / "runs.jsonl")} == run_ids
    assert {r["run_id"] for r in rows(directory / "events.jsonl")} == run_ids
    assert {r["run_id"] for r in rows(directory / "reflections.jsonl")} == run_ids
    scores = rows(directory / "scores.jsonl")
    assert {s["candidate"] for s in scores} == set(demo.MEN)


def test_every_run_row_has_its_reproducibility_fields(tmp_path):
    directory, _ = simulate(tmp_path)
    for run in rows(directory / "runs.jsonl"):
        assert RUN_FIELDS <= set(run)
        assert run["prompt_version"] and run["temperature"]["choice"] and run["model"].startswith("fake:")


def test_a_prompt_version_maps_to_the_exact_prompt_text(tmp_path):
    directory, _ = simulate(tmp_path)
    version = rows(directory / "runs.jsonl")[0]["prompt_version"]
    saved = json.loads((tmp_path / "prompts" / f"{version}.json").read_text())
    assert saved == json.loads(json.dumps(prompts.prompt_texts()))
    assert prompts.prompt_version(saved) == version


def test_changing_any_prompt_text_changes_the_version():
    texts = prompts.prompt_texts()
    changed = dict(texts, rumour=texts["rumour"] + " ")
    assert prompts.prompt_version(changed) != prompts.prompt_version(texts)
