from fastapi import APIRouter, HTTPException

from backend.app.models.run import RunRecord, RunSummary
from backend.app.models.simulation_request import SimulationRunRequest
from backend.app.services.run_repository import get_run_record, list_run_summaries
from backend.app.services.simulation_service import simulate_run


router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=list[RunSummary])
def get_runs() -> list[RunSummary]:
    return list_run_summaries()


@router.get("/{run_id}", response_model=RunRecord)
def get_run_by_id(run_id: str) -> RunRecord:
    run = get_run_record(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    return run


@router.post("/simulate", response_model=RunRecord)
def create_simulated_run(payload: SimulationRunRequest | None = None) -> RunRecord:
    return simulate_run(payload)
