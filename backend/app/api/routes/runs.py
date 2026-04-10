import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.core.config import get_settings
from backend.app.models.run import RunRecord, RunSummary
from backend.app.models.simulation import (
    RunDetailExportArtifacts,
    RunDetailResponse,
    RunEventStreamPayload,
    RunShockRequest,
    RunShockResponse,
)
from backend.app.services.event_repository import get_run_event_log
from backend.app.services.export_repository import get_simulation_export_bundle
from backend.app.services.run_repository import get_run_record, list_run_summaries
from backend.app.services.shock_registry import build_pending_shock, get_shock_registry


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


@router.get("/{run_id}/detail", response_model=RunDetailResponse)
def get_run_detail(run_id: str) -> RunDetailResponse:
    run = get_run_record(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    settings = get_settings()
    event_log = get_run_event_log(settings.events_dir, run_id)
    export_bundle = get_simulation_export_bundle(settings.exports_dir, run_id)

    return RunDetailResponse(
        run=run,
        event_log=event_log,
        trace_metadata=export_bundle["trace_metadata"] if export_bundle else None,
        export_artifacts=(
            RunDetailExportArtifacts(**export_bundle["paths"])
            if export_bundle
            else None
        ),
        derived=(
            export_bundle["summary"].get("derived")
            if export_bundle and export_bundle.get("summary")
            else None
        ),
        conversation=(
            export_bundle["conversation"].get("messages")
            if export_bundle and export_bundle.get("conversation")
            else _build_conversation_from_run(run)
        ),
    )


@router.post("/{run_id}/shock", response_model=RunShockResponse)
def queue_run_shock(run_id: str, payload: RunShockRequest) -> RunShockResponse:
    try:
        pending = build_pending_shock(payload.shock_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    queued = get_shock_registry().register(run_id, pending)
    return RunShockResponse(
        run_id=run_id,
        shock_type=queued.shock_type,
        multiplier=queued.multiplier,
        headline=queued.headline,
        consumed=queued.consumed,
        queued_at=queued.queued_at,
    )


@router.get("/{run_id}/events")
async def stream_run_events(run_id: str) -> StreamingResponse:
    settings = get_settings()

    async def event_generator():
        emitted_count = 0
        heartbeat_ticks = 0

        while True:
            event_log = get_run_event_log(settings.events_dir, run_id)
            events = event_log.events if event_log is not None else []

            if emitted_count < len(events):
                for event in events[emitted_count:]:
                    payload = RunEventStreamPayload(
                        run_id=run_id,
                        event=event,
                    ).model_dump(mode="json")
                    yield f"event: run-event\ndata: {json.dumps(payload)}\n\n"
                emitted_count = len(events)
                heartbeat_ticks = 0
            else:
                heartbeat_ticks += 1
                if heartbeat_ticks >= 8:
                    yield ": keep-alive\n\n"
                    heartbeat_ticks = 0

            run = get_run_record(run_id)
            if run is not None and run.status.value != "running" and emitted_count >= len(events):
                break

            await asyncio.sleep(0.75)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _build_conversation_from_run(run: RunRecord) -> list[dict]:
    agent_map = {agent.id: agent for agent in run.agents}
    messages: list[dict] = []
    for step in run.steps:
        agent = agent_map.get(step.agent_id)
        speaker_name = (
            "Market Desk"
            if step.agent_id == "market_desk"
            else agent.name if agent is not None else step.agent_id
        )
        messages.append(
            {
                "index": step.index,
                "timestamp": step.created_at,
                "phase": step.phase,
                "round": step.round_number,
                "speaker_id": step.agent_id,
                "speaker_name": speaker_name,
                "speaker_role": agent.role if agent is not None else None,
                "kind": step.kind,
                "message": step.message,
                "outcome": step.outcome,
                "offer_price": step.proposed_price,
                "delivered_message": (
                    step.delivered_message.model_dump(mode="json")
                    if step.delivered_message is not None
                    else None
                ),
                "currency": run.product_context.currency,
            }
        )

    return messages
