from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.models.run import RunRecord


class PipelineDependencyStatus(BaseModel):
    configured: bool
    available: bool
    message: str


class PipelineExportRecord(BaseModel):
    file_path: str
    created_at: datetime


class SimulationTestPipelineResult(BaseModel):
    success: bool
    message: str
    run_id: str
    trace_id: str | None = None
    export: PipelineExportRecord | None = None
    openai: PipelineDependencyStatus
    langfuse: PipelineDependencyStatus
    events: list[str] = Field(default_factory=list)


class SimulationBatchResult(BaseModel):
    seed: int
    count: int
    runs: list[RunRecord]
