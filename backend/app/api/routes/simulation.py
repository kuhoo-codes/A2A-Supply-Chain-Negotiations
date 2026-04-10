from fastapi import APIRouter, HTTPException

from backend.app.models.run import RunRecord
from backend.app.models.simulation_request import SimulationRunRequest
from backend.app.models.simulation import SimulationTestPipelineResult
from backend.app.services.simulation_service import (
    SimulationExecutionError,
    run_test_pipeline,
    simulate_run,
)


router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.post("/run", response_model=RunRecord)
def run_simulation(payload: SimulationRunRequest) -> RunRecord:
    try:
        return simulate_run(payload)
    except SimulationExecutionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/test-pipeline", response_model=SimulationTestPipelineResult)
def test_pipeline(payload: SimulationRunRequest) -> SimulationTestPipelineResult:
    return run_test_pipeline(payload)
