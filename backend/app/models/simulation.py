from datetime import datetime

from pydantic import BaseModel, Field


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
