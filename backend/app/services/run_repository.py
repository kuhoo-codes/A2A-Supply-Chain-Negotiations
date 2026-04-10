from pathlib import Path

from backend.app.models.run import RunRecord, RunSummary
from backend.app.services.json_store import ensure_directory, read_json, write_json


ROOT_DIR = Path(__file__).resolve().parents[3]
RUNS_DIR = ROOT_DIR / "runs"


def list_run_summaries() -> list[RunSummary]:
    ensure_directory(RUNS_DIR)

    summaries: list[RunSummary] = []
    for file_path in RUNS_DIR.glob("*.json"):
        run = RunRecord.model_validate(read_json(file_path))
        summaries.append(run.to_summary())

    return sorted(summaries, key=lambda item: item.updated_at, reverse=True)


def get_run_record(run_id: str) -> RunRecord | None:
    ensure_directory(RUNS_DIR)

    file_path = _run_path(run_id)
    if not file_path.exists():
        return None

    return RunRecord.model_validate(read_json(file_path))


def save_run_record(run: RunRecord) -> None:
    write_json(_run_path(run.id), run.model_dump(mode="json"))


def _run_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"
