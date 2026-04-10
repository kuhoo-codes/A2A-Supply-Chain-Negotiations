from fastapi import APIRouter, HTTPException

from backend.app.models.simulation import SimulationBatchLaunchResult, SimulationTestPipelineResult
from backend.app.models.simulation_request import SimulationSeedRequest
from backend.app.services.simulation_service import (
    SimulationExecutionError,
    launch_seeded_simulations,
    run_test_pipeline,
)


router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.post("/run", response_model=SimulationBatchLaunchResult)
def run_simulation(
    payload: SimulationSeedRequest,
) -> SimulationBatchLaunchResult:
    try:
        return launch_seeded_simulations(payload)
    except SimulationExecutionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/test-pipeline", response_model=SimulationTestPipelineResult)
def test_pipeline(payload: SimulationSeedRequest) -> SimulationTestPipelineResult:
    return run_test_pipeline(payload)
