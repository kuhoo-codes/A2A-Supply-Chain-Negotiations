import json
from random import Random
from threading import Thread
from uuid import uuid4

from backend.app.clients.langfuse_client import LangfuseTraceWrapper
from backend.app.clients.openai_client import OpenAIDecisionError, OpenAIClientWrapper
from backend.app.core.config import get_settings
from backend.app.models.run import (
    Agent,
    AgentRole,
    DiagnosisSummary,
    NegotiationRecord,
    NegotiationStatus,
    NegotiationStep,
    Phase,
    PhaseName,
    ProductMarketContext,
    ReservationPrices,
    RunEvent,
    RunEventLog,
    RunEventType,
    RunRecord,
    RunStatus,
    ToolCallEvent,
    utc_now,
)
from backend.app.models.simulation import (
    SimulationBatchLaunchResult,
    PipelineDependencyStatus,
    PipelineExportRecord,
    SimulationTestPipelineResult,
)
from backend.app.models.simulation_request import SimulationRunConfig, SimulationSeedRequest
from backend.app.services.event_repository import save_run_event_log
from backend.app.services.export_repository import save_simulation_export_bundle
from backend.app.services.run_repository import get_run_record, save_run_record
from backend.app.services.shock_registry import get_shock_registry


class SimulationExecutionError(Exception):
    pass


MAX_AGENT_TURNS_PER_NEGOTIATION = 15


class RunEventCollector:
    def __init__(self, run_id: str, created_at) -> None:
        self.run_id = run_id
        self.created_at = created_at
        self.events: list[RunEvent] = []

    def log(
        self,
        *,
        event_type: RunEventType,
        timestamp=None,
        phase: PhaseName | None = None,
        round_number: int | None = None,
        agent: str | None = None,
        observed_market_price: float | None = None,
        offer_price: float | None = None,
        action: str | None = None,
        status: str | None = None,
        note: str | None = None,
        reasoning_summary: str | None = None,
        negotiation_id: str | None = None,
        tool_name: str | None = None,
        previous_market_price: float | None = None,
        shock_type: str | None = None,
        shock_multiplier: float | None = None,
        shock_headline: str | None = None,
    ) -> None:
        self.events.append(
            RunEvent(
                run_id=self.run_id,
                timestamp=timestamp or utc_now(),
                phase=phase,
                round=round_number,
                agent=agent,
                event_type=event_type,
                observed_market_price=observed_market_price,
                offer_price=offer_price,
                action=action,
                status=status,
                note=note,
                reasoning_summary=reasoning_summary,
                negotiation_id=negotiation_id,
                tool_name=tool_name,
                previous_market_price=previous_market_price,
                shock_type=shock_type,
                shock_multiplier=shock_multiplier,
                shock_headline=shock_headline,
            )
        )

    def build_log(self) -> RunEventLog:
        updated_at = self.events[-1].timestamp if self.events else self.created_at
        return RunEventLog(
            run_id=self.run_id,
            created_at=self.created_at,
            updated_at=updated_at,
            events=self.events,
        )


class SimulationRunExecutionResult:
    def __init__(
        self,
        *,
        run: RunRecord,
        event_log: RunEventLog,
        trace_id: str | None,
        trace_url: str | None,
        export_paths: dict[str, str] | None = None,
        failure_point: dict | None = None,
        failure_type: str | None = None,
    ) -> None:
        self.run = run
        self.event_log = event_log
        self.trace_id = trace_id
        self.trace_url = trace_url
        self.export_paths = export_paths
        self.failure_point = failure_point
        self.failure_type = failure_type


class RunSnapshotWriter:
    def __init__(
        self,
        *,
        run_id: str,
        title: str,
        scenario: str,
        created_at,
        product_context: ProductMarketContext,
        agents: list[Agent],
        phases: list[Phase],
        max_rounds_per_negotiation: int,
    ) -> None:
        self.run_id = run_id
        self.title = title
        self.scenario = scenario
        self.created_at = created_at
        self.product_context = product_context
        self.agents = agents
        self.phases = phases
        self.max_rounds_per_negotiation = max_rounds_per_negotiation

    def save(
        self,
        *,
        status: RunStatus,
        steps: list[NegotiationStep],
        negotiations: list[NegotiationRecord],
        diagnosis: DiagnosisSummary,
        updated_at=None,
        notes: str = "Backend simulation with linked upstream and downstream negotiations.",
    ) -> RunRecord:
        run = RunRecord(
            id=self.run_id,
            title=self.title,
            status=status,
            scenario=self.scenario,
            created_at=self.created_at,
            updated_at=updated_at or utc_now(),
            product_context=self.product_context,
            agents=self.agents,
            phases=self.phases,
            steps=steps,
            negotiations=negotiations,
            diagnosis=diagnosis,
            max_rounds_per_negotiation=self.max_rounds_per_negotiation,
            notes=notes,
            tags=["simulation", "supply-chain"],
        )
        save_run_record(run)
        return run


def simulate_run(request: SimulationRunConfig | None) -> RunRecord:
    return _execute_simulation_run(request).run


def _execute_simulation_run(
    request: SimulationRunConfig | None,
    *,
    run_id: str | None = None,
    created_at=None,
) -> SimulationRunExecutionResult:
    if request is None:
        raise SimulationExecutionError("Simulation input is required.")

    simulation_request = request
    created_at = created_at or utc_now()
    run_id = run_id or f"run-{uuid4().hex[:10]}"
    event_collector = RunEventCollector(run_id=run_id, created_at=created_at)
    settings = get_settings()
    langfuse_wrapper = LangfuseTraceWrapper(settings)
    trace_id: str | None = None
    trace_url: str | None = None
    scenario = (
        f"{simulation_request.product_name} in {simulation_request.market_region}. "
        f"Supplier-to-manufacturer pricing sets the manufacturer cost basis before the retailer negotiation."
    )
    event_collector.log(
        event_type=RunEventType.RUN_START,
        timestamp=created_at,
        status=RunStatus.RUNNING.value,
        note=f"Starting {simulation_request.title}.",
    )

    with langfuse_wrapper.start_span(
        name="simulation-run",
        input={
            "title": simulation_request.title,
            "product_name": simulation_request.product_name,
            "product_category": simulation_request.product_category,
            "market_region": simulation_request.market_region,
            "target_quantity": simulation_request.target_quantity,
            "max_rounds_per_negotiation": simulation_request.max_rounds_per_negotiation,
        },
        metadata={
            "run_id": run_id,
            "component": "simulation",
        },
        status_message="Simulation run started.",
    ) as run_trace:
        openai_wrapper = OpenAIClientWrapper(settings)
        openai_configured, openai_available, openai_message = openai_wrapper.get_status()
        trace_id = langfuse_wrapper.get_current_trace_id()
        trace_url = langfuse_wrapper.get_trace_url(trace_id=trace_id)
        if not openai_configured or not openai_available:
            raise SimulationExecutionError(openai_message)

        supplier = Agent(
            id="supplier",
            name="Supplier",
            role=AgentRole.SUPPLIER,
            objective="Sell above the supplier reservation price while keeping volume committed.",
            reservation_prices=ReservationPrices(
                min_sell_price=simulation_request.supplier_min_sell_price
            ),
        )
        manufacturer = Agent(
            id="manufacturer",
            name="Manufacturer",
            role=AgentRole.MANUFACTURER,
            objective="Buy below the procurement ceiling and preserve downstream margin.",
            reservation_prices=ReservationPrices(
                min_sell_price=simulation_request.manufacturer_min_sell_price,
                max_buy_price=simulation_request.manufacturer_max_buy_price,
            ),
        )
        retailer = Agent(
            id="retailer",
            name="Retailer",
            role=AgentRole.RETAILER,
            objective="Buy enough units without exceeding the retail reservation price.",
            reservation_prices=ReservationPrices(
                max_buy_price=simulation_request.retailer_max_buy_price
            ),
        )
        phases = _build_phases()
        product_context = ProductMarketContext(
            product_name=simulation_request.product_name,
            product_category=simulation_request.product_category,
            market_region=simulation_request.market_region,
            baseline_unit_price=simulation_request.baseline_unit_price,
            target_quantity=simulation_request.target_quantity,
            currency=simulation_request.currency,
            demand_signal=simulation_request.demand_signal,
            supply_signal=simulation_request.supply_signal,
        )
        snapshot_writer = RunSnapshotWriter(
            run_id=run_id,
            title=simulation_request.title,
            scenario=scenario,
            created_at=created_at,
            product_context=product_context,
            agents=[supplier, manufacturer, retailer],
            phases=phases,
            max_rounds_per_negotiation=simulation_request.max_rounds_per_negotiation,
        )
        running_diagnosis = DiagnosisSummary(
            outcome="Simulation is running.",
            chain_effect="Live negotiation activity will appear as each agent turn is persisted.",
            key_risks=["Live data is incomplete until both negotiations finish."],
            key_signals=["Run initialized and waiting for agent decisions."],
            suggested_next_actions=["Open the run detail page to watch the transcript build in real time."],
        )
        snapshot_writer.save(
            status=RunStatus.RUNNING,
            steps=[],
            negotiations=[],
            diagnosis=running_diagnosis,
            updated_at=created_at,
            notes="Simulation has started and will update this record incrementally.",
        )
        save_run_event_log(settings.events_dir, event_collector.build_log())
        try:
            event_collector.log(
                event_type=RunEventType.PHASE_START,
                phase=PhaseName.SUPPLIER_MANUFACTURER,
                status=NegotiationStatus.OPEN.value,
                note="Initial upstream procurement negotiation started.",
            )
            save_run_event_log(settings.events_dir, event_collector.build_log())
            with langfuse_wrapper.start_span(
                name="negotiation-phase",
                input={
                    "phase": PhaseName.SUPPLIER_MANUFACTURER.value,
                    "seller_id": supplier.id,
                    "buyer_id": manufacturer.id,
                    "min_sell_price": simulation_request.supplier_min_sell_price,
                    "max_buy_price": simulation_request.manufacturer_max_buy_price,
                    "quantity": simulation_request.target_quantity,
                    "max_rounds": simulation_request.max_rounds_per_negotiation,
                },
                metadata={
                    "run_id": run_id,
                    "phase": PhaseName.SUPPLIER_MANUFACTURER.value,
                    "phase_label": "Supplier to Manufacturer",
                },
                status_message="Negotiation phase started.",
            ) as first_phase_trace:
                first_result = _simulate_negotiation(
                    openai_wrapper=openai_wrapper,
                    langfuse_wrapper=langfuse_wrapper,
                    run_id=run_id,
                    phase=PhaseName.SUPPLIER_MANUFACTURER,
                    label="Supplier to Manufacturer",
                    product_name=simulation_request.product_name,
                    reference_market_price=simulation_request.baseline_unit_price,
                    seller=supplier,
                    buyer=manufacturer,
                    min_sell_price=simulation_request.supplier_min_sell_price,
                    max_buy_price=simulation_request.manufacturer_max_buy_price,
                    quantity=simulation_request.target_quantity,
                    max_rounds=simulation_request.max_rounds_per_negotiation,
                    step_index_start=1,
                    dependency_note="Initial upstream procurement negotiation.",
                    event_collector=event_collector,
                    on_step=lambda current_steps: _persist_running_snapshot(
                        snapshot_writer=snapshot_writer,
                        event_collector=event_collector,
                        settings=settings,
                        steps=current_steps,
                        negotiations=[],
                    ),
                )
                first_phase_trace.update(
                    output={
                        "status": first_result.record.status.value,
                        "rounds_completed": first_result.record.rounds_completed,
                        "final_price": first_result.record.final_price,
                    },
                    status_message=first_result.record.outcome_summary,
                )
            event_collector.log(
                event_type=RunEventType.PHASE_END,
                phase=first_result.record.phase,
                round_number=first_result.record.rounds_completed,
                status=first_result.record.status.value,
                offer_price=first_result.record.final_price,
                negotiation_id=first_result.record.id,
                note=first_result.record.outcome_summary,
            )
            _persist_running_snapshot(
                snapshot_writer=snapshot_writer,
                event_collector=event_collector,
                settings=settings,
                steps=first_result.steps,
                negotiations=[first_result.record],
            )

            second_result: NegotiationSimulationResult | None = None
            manufacturer_cost_basis: float | None = None
            manufacturer_sell_floor: float | None = None

            if (
                first_result.record.status == NegotiationStatus.ACCEPTED
                and first_result.record.final_price is not None
            ):
                manufacturer_cost_basis = first_result.record.final_price
                manufacturer_sell_floor = max(
                    simulation_request.manufacturer_min_sell_price,
                    round(
                        manufacturer_cost_basis + simulation_request.manufacturer_margin_floor,
                        2,
                    ),
                )

                event_collector.log(
                    event_type=RunEventType.PHASE_START,
                    phase=PhaseName.MANUFACTURER_RETAILER,
                    status=NegotiationStatus.OPEN.value,
                    offer_price=manufacturer_sell_floor,
                    note=(
                        "Downstream negotiation started with the accepted upstream deal as cost basis."
                    ),
                )
                save_run_event_log(settings.events_dir, event_collector.build_log())
                with langfuse_wrapper.start_span(
                    name="negotiation-phase",
                    input={
                        "phase": PhaseName.MANUFACTURER_RETAILER.value,
                        "seller_id": manufacturer.id,
                        "buyer_id": retailer.id,
                        "min_sell_price": manufacturer_sell_floor,
                        "max_buy_price": simulation_request.retailer_max_buy_price,
                        "quantity": simulation_request.target_quantity,
                        "max_rounds": simulation_request.max_rounds_per_negotiation,
                        "manufacturer_cost_basis": manufacturer_cost_basis,
                    },
                    metadata={
                        "run_id": run_id,
                        "phase": PhaseName.MANUFACTURER_RETAILER.value,
                        "phase_label": "Manufacturer to Retailer",
                    },
                    status_message="Negotiation phase started.",
                ) as second_phase_trace:
                    second_result = _simulate_negotiation(
                        openai_wrapper=openai_wrapper,
                        langfuse_wrapper=langfuse_wrapper,
                        run_id=run_id,
                        phase=PhaseName.MANUFACTURER_RETAILER,
                        label="Manufacturer to Retailer",
                        product_name=simulation_request.product_name,
                        reference_market_price=simulation_request.baseline_unit_price,
                        seller=manufacturer,
                        buyer=retailer,
                        min_sell_price=manufacturer_sell_floor,
                        max_buy_price=simulation_request.retailer_max_buy_price,
                        quantity=simulation_request.target_quantity,
                        max_rounds=simulation_request.max_rounds_per_negotiation,
                        step_index_start=len(first_result.steps) + 1,
                        dependency_note=(
                            "Manufacturer sell floor uses the accepted upstream deal as its cost basis."
                        ),
                        event_collector=event_collector,
                        on_step=lambda current_steps: _persist_running_snapshot(
                            snapshot_writer=snapshot_writer,
                            event_collector=event_collector,
                            settings=settings,
                            steps=[*first_result.steps, *current_steps],
                            negotiations=[first_result.record],
                        ),
                    )
                    second_phase_trace.update(
                        output={
                            "status": second_result.record.status.value,
                            "rounds_completed": second_result.record.rounds_completed,
                            "final_price": second_result.record.final_price,
                        },
                        status_message=second_result.record.outcome_summary,
                    )
                event_collector.log(
                    event_type=RunEventType.PHASE_END,
                    phase=second_result.record.phase,
                    round_number=second_result.record.rounds_completed,
                    status=second_result.record.status.value,
                    offer_price=second_result.record.final_price,
                    negotiation_id=second_result.record.id,
                    note=second_result.record.outcome_summary,
                )
                _persist_running_snapshot(
                    snapshot_writer=snapshot_writer,
                    event_collector=event_collector,
                    settings=settings,
                    steps=[*first_result.steps, *second_result.steps],
                    negotiations=[first_result.record, second_result.record],
                )

            negotiations = [first_result.record]
            all_steps = [*first_result.steps]
            if second_result is not None:
                negotiations.append(second_result.record)
                all_steps.extend(second_result.steps)

            status = _resolve_run_status(negotiations)
            diagnosis = _build_diagnosis(
                first_negotiation=first_result.record,
                second_negotiation=second_result.record if second_result else None,
                manufacturer_sell_floor=manufacturer_sell_floor,
                manufacturer_cost_basis=manufacturer_cost_basis,
                currency=simulation_request.currency,
            )

            event_collector.log(
                event_type=RunEventType.FINAL_OUTCOME,
                status=status.value,
                note=diagnosis.outcome,
                reasoning_summary=diagnosis.chain_effect,
            )

            run = RunRecord(
                id=run_id,
                title=simulation_request.title,
                status=status,
                scenario=scenario,
                created_at=created_at,
                updated_at=utc_now(),
                product_context=product_context,
                agents=[supplier, manufacturer, retailer],
                phases=phases,
                steps=all_steps,
                negotiations=negotiations,
                diagnosis=diagnosis,
                max_rounds_per_negotiation=simulation_request.max_rounds_per_negotiation,
                notes="Backend simulation with linked upstream and downstream negotiations.",
                tags=["simulation", "supply-chain"],
            )
            save_run_record(run)
            event_collector.log(
                event_type=RunEventType.RUN_END,
                status=status.value,
                note="Run record and event log persisted.",
            )
            event_log = event_collector.build_log()
            save_run_event_log(settings.events_dir, event_log)
            langfuse_configured, langfuse_available, langfuse_message = langfuse_wrapper.get_status()
            export_paths = save_simulation_export_bundle(
                exports_dir=settings.exports_dir,
                run_id=run.id,
                summary_payload=_build_export_summary_payload(
                    run=run,
                    event_log=event_log,
                    trace_id=trace_id,
                    trace_url=trace_url,
                ),
                event_log_payload=event_log.model_dump(mode="json"),
                trace_payload=_build_trace_export_payload(
                    run=run,
                    trace_id=trace_id,
                    trace_url=trace_url,
                    langfuse_status=langfuse_message,
                    langfuse_available=langfuse_available,
                    langfuse_configured=langfuse_configured,
                ),
                conversation_payload=_build_conversation_export_payload(run=run),
            )
            run_trace.update(
                output={
                    "run_id": run.id,
                    "status": run.status.value,
                    "negotiations": [record.model_dump(mode="json") for record in run.negotiations],
                    "diagnosis": run.diagnosis.model_dump(mode="json"),
                },
                metadata={
                    "run_id": run_id,
                    "trace_url": trace_url,
                },
                status_message="Simulation run completed.",
            )
            langfuse_wrapper.flush()
            return SimulationRunExecutionResult(
                run=run,
                event_log=event_log,
                trace_id=trace_id,
                trace_url=trace_url,
                export_paths={key: str(value) for key, value in export_paths.items()},
                failure_point=None,
                failure_type=None,
            )
        except Exception as exc:
            existing_run = get_run_record(run_id)
            failed_diagnosis = DiagnosisSummary(
                outcome=f"Simulation failed: {exc}",
                chain_effect="The run terminated before all negotiation phases were persisted.",
                key_risks=["The live transcript may be partial."],
                key_signals=["Backend raised an execution error."],
                suggested_next_actions=["Inspect the event log for the last completed agent turn."],
            )
            snapshot_writer.save(
                status=RunStatus.FAILED,
                steps=existing_run.steps if existing_run is not None else [],
                negotiations=existing_run.negotiations if existing_run is not None else [],
                diagnosis=failed_diagnosis,
                updated_at=utc_now(),
                notes="Simulation failed before completion.",
            )
            event_collector.log(
                event_type=RunEventType.FINAL_OUTCOME,
                status=RunStatus.FAILED.value,
                note=str(exc),
            )
            event_collector.log(
                event_type=RunEventType.RUN_END,
                status=RunStatus.FAILED.value,
                note="Run ended with an error before completion.",
                reasoning_summary=str(exc),
            )
            event_log = event_collector.build_log()
            save_run_event_log(settings.events_dir, event_log)
            run_trace.update(
                output={"error": str(exc), "run_id": run_id},
                metadata={"run_id": run_id, "trace_url": trace_url},
                status_message=str(exc),
                level="ERROR",
            )
            langfuse_wrapper.flush()
            raise


def launch_seeded_simulations(
    request: SimulationSeedRequest,
) -> SimulationBatchLaunchResult:
    openai_configured, openai_available, openai_message = OpenAIClientWrapper(
        get_settings()
    ).get_status()
    if not openai_configured or not openai_available:
        raise SimulationExecutionError(openai_message)

    launched_runs: list[RunRecord] = []
    for config in _build_seeded_requests(request.seed):
        created_at = utc_now()
        run_id = f"run-{uuid4().hex[:10]}"
        launched_runs.append(_create_pending_run(config, run_id=run_id, created_at=created_at))
        Thread(
            target=_run_simulation_in_background,
            args=(config, run_id, created_at),
            daemon=True,
            name=f"simulation-{run_id}",
        ).start()

    return SimulationBatchLaunchResult(
        seed=request.seed,
        count=len(launched_runs),
        runs=launched_runs,
    )


def _compose_public_message(*, note: str, fallback: str) -> str:
    cleaned_note = note.strip()
    return cleaned_note or fallback


def _compose_private_reasoning(*, reason: str, reservation_diagnostic: str | None) -> str | None:
    return "\n".join(
        value
        for value in [reason.strip() or None, reservation_diagnostic]
        if value
    ) or None


def _reservation_diagnostic(
    *,
    agent: Agent,
    is_seller: bool,
    action: str,
    proposed_price: float | None,
    delivered_message: dict | None,
) -> str | None:
    reservation = agent.reservation_prices
    pending_offer_price = _coerce_price(delivered_message.get("price")) if delivered_message else None

    if action == "make_offer" and proposed_price is not None:
        if is_seller and reservation.min_sell_price is not None and proposed_price < reservation.min_sell_price:
            return (
                f"Reservation-price violation: {agent.name} offered {proposed_price:.2f}, "
                f"below its hidden seller floor of {reservation.min_sell_price:.2f}."
            )
        if (not is_seller) and reservation.max_buy_price is not None and proposed_price > reservation.max_buy_price:
            return (
                f"Reservation-price violation: {agent.name} offered {proposed_price:.2f}, "
                f"above its hidden buyer ceiling of {reservation.max_buy_price:.2f}."
            )

    if action == "accept_offer" and pending_offer_price is not None:
        if is_seller and reservation.min_sell_price is not None and pending_offer_price < reservation.min_sell_price:
            return (
                f"Reservation-price violation: {agent.name} accepted {pending_offer_price:.2f}, "
                f"below its hidden seller floor of {reservation.min_sell_price:.2f}."
            )
        if (not is_seller) and reservation.max_buy_price is not None and pending_offer_price > reservation.max_buy_price:
            return (
                f"Reservation-price violation: {agent.name} accepted {pending_offer_price:.2f}, "
                f"above its hidden buyer ceiling of {reservation.max_buy_price:.2f}."
            )

    return None


def _run_simulation_in_background(
    config: SimulationRunConfig,
    run_id: str,
    created_at,
) -> None:
    try:
        _execute_simulation_run(config, run_id=run_id, created_at=created_at)
    except Exception:
        return None


def _create_pending_run(
    config: SimulationRunConfig,
    *,
    run_id: str,
    created_at,
) -> RunRecord:
    supplier = Agent(
        id="supplier",
        name="Supplier",
        role=AgentRole.SUPPLIER,
        objective="Sell above the supplier reservation price while keeping volume committed.",
        reservation_prices=ReservationPrices(min_sell_price=config.supplier_min_sell_price),
    )
    manufacturer = Agent(
        id="manufacturer",
        name="Manufacturer",
        role=AgentRole.MANUFACTURER,
        objective="Buy below the procurement ceiling and preserve downstream margin.",
        reservation_prices=ReservationPrices(
            min_sell_price=config.manufacturer_min_sell_price,
            max_buy_price=config.manufacturer_max_buy_price,
        ),
    )
    retailer = Agent(
        id="retailer",
        name="Retailer",
        role=AgentRole.RETAILER,
        objective="Buy enough units without exceeding the retail reservation price.",
        reservation_prices=ReservationPrices(max_buy_price=config.retailer_max_buy_price),
    )
    run = RunRecord(
        id=run_id,
        title=config.title,
        status=RunStatus.RUNNING,
        scenario=(
            f"{config.product_name} in {config.market_region}. "
            f"Supplier-to-manufacturer pricing sets the manufacturer cost basis before the retailer negotiation."
        ),
        created_at=created_at,
        updated_at=created_at,
        product_context=ProductMarketContext(
            product_name=config.product_name,
            product_category=config.product_category,
            market_region=config.market_region,
            baseline_unit_price=config.baseline_unit_price,
            target_quantity=config.target_quantity,
            currency=config.currency,
            demand_signal=config.demand_signal,
            supply_signal=config.supply_signal,
        ),
        agents=[supplier, manufacturer, retailer],
        phases=_build_phases(),
        steps=[],
        negotiations=[],
        diagnosis=DiagnosisSummary(
            outcome="Simulation is running.",
            chain_effect="Live updates will appear as soon as each agent turn is persisted.",
            key_risks=["This record is incomplete while execution is in progress."],
            key_signals=["Run has been queued and initialized."],
            suggested_next_actions=["Open the run to watch the chat and event log update in real time."],
        ),
        max_rounds_per_negotiation=config.max_rounds_per_negotiation,
        notes="Simulation has started and will update this record incrementally.",
        tags=["simulation", "supply-chain"],
    )
    save_run_record(run)
    save_run_event_log(
        get_settings().events_dir,
        RunEventLog(
            run_id=run_id,
            created_at=created_at,
            updated_at=created_at,
            events=[
                RunEvent(
                    run_id=run_id,
                    timestamp=created_at,
                    event_type=RunEventType.RUN_START,
                    status=RunStatus.RUNNING.value,
                    note=f"Starting {config.title}.",
                )
            ],
        ),
    )
    return run


def _persist_running_snapshot(
    *,
    snapshot_writer: RunSnapshotWriter,
    event_collector: RunEventCollector,
    settings,
    steps: list[NegotiationStep],
    negotiations: list[NegotiationRecord],
) -> None:
    snapshot_writer.save(
        status=RunStatus.RUNNING,
        steps=steps,
        negotiations=negotiations,
        diagnosis=DiagnosisSummary(
            outcome="Simulation is running.",
            chain_effect="Live negotiation activity is being written to the transcript as each step completes.",
            key_risks=["Final diagnosis and derived metrics are not complete yet."],
            key_signals=[f"{len(steps)} transcript steps persisted.", f"{len(negotiations)} negotiations resolved so far."],
            suggested_next_actions=["Keep this page open to watch additional messages arrive."],
        ),
        updated_at=utc_now(),
        notes="Simulation is still running and this snapshot is live.",
    )
    save_run_event_log(settings.events_dir, event_collector.build_log())


def run_test_pipeline(request: SimulationSeedRequest | None = None) -> SimulationTestPipelineResult:
    settings = get_settings()
    openai_wrapper = OpenAIClientWrapper(settings)
    langfuse_wrapper = LangfuseTraceWrapper(settings)
    openai_configured, openai_available, openai_message = openai_wrapper.get_status()
    langfuse_configured, langfuse_available, langfuse_message = langfuse_wrapper.get_status()
    events: list[str] = []

    try:
        if request is None:
            raise SimulationExecutionError("Seed input is required.")
        batch_requests = _build_seeded_requests(request.seed)
        first_execution = _execute_simulation_run(batch_requests[0])
        run = first_execution.run
        for item in batch_requests[1:]:
            simulate_run(item)
    except SimulationExecutionError as exc:
        return SimulationTestPipelineResult(
            success=False,
            message=str(exc),
            run_id="",
            trace_id=None,
            export=None,
            openai=PipelineDependencyStatus(
                configured=openai_configured,
                available=openai_available,
                message=openai_message,
            ),
            langfuse=PipelineDependencyStatus(
                configured=langfuse_configured,
                available=langfuse_available,
                message=langfuse_message,
            ),
            events=["Simulation did not start because the LLM decision step was unavailable."],
        )

    events.append(f"Simulated run {run.id} and persisted it to local storage.")

    trace_id = first_execution.trace_id
    if trace_id:
        events.append(f"Initialized trace {trace_id}.")
    else:
        events.append("Skipped trace initialization because Langfuse is unavailable.")

    export_paths = first_execution.export_paths or {}
    if export_paths.get("summary"):
        events.append(f"Saved simulation export bundle to {run.id}.")

    success = True
    message = "Simulation pipeline completed."
    if not openai_available and openai_configured:
        message = "Simulation completed, but the OpenAI client is unavailable."
    if not langfuse_available and langfuse_configured:
        message = "Simulation completed, but tracing configuration is incomplete."

    return SimulationTestPipelineResult(
        success=success,
        message=message,
        run_id=run.id,
        trace_id=trace_id,
        export=PipelineExportRecord(
            file_path=export_paths.get("summary", ""),
            created_at=run.updated_at,
            event_log_path=export_paths.get("event_log"),
            trace_path=export_paths.get("trace"),
            conversation_path=export_paths.get("conversation"),
        ),
        openai=PipelineDependencyStatus(
            configured=openai_configured,
            available=openai_available,
            message=openai_message,
        ),
        langfuse=PipelineDependencyStatus(
            configured=langfuse_configured,
            available=langfuse_available,
            message=langfuse_message,
        ),
        events=events,
    )


class NegotiationSimulationResult:
    def __init__(self, record: NegotiationRecord, steps: list[NegotiationStep]) -> None:
        self.record = record
        self.steps = steps


def _log_tool_events(
    event_collector: RunEventCollector,
    langfuse_wrapper: LangfuseTraceWrapper,
    run_id: str,
    phase: PhaseName,
    round_number: int,
    negotiation_id: str,
    agent_id: str,
    tool_calls: list[ToolCallEvent],
    status: str,
) -> None:
    for tool_call in tool_calls:
        observed_market_price = tool_call.arguments.get("observed_market_price")
        market_price = (
            float(observed_market_price)
            if isinstance(observed_market_price, (int, float))
            else None
        )
        previous_market_price = tool_call.arguments.get("base_market_price")
        prior_price = (
            float(previous_market_price)
            if isinstance(previous_market_price, (int, float))
            else None
        )
        shock_multiplier_value = tool_call.arguments.get("shock_multiplier")
        shock_multiplier = (
            float(shock_multiplier_value)
            if isinstance(shock_multiplier_value, (int, float))
            else None
        )
        shock_type = (
            str(tool_call.arguments.get("shock_type"))
            if tool_call.arguments.get("shock_type") is not None
            else None
        )
        shock_headline = (
            str(tool_call.arguments.get("shock_headline"))
            if tool_call.arguments.get("shock_headline") is not None
            else None
        )
        with langfuse_wrapper.start_tool(
            name=tool_call.tool_name,
            input=tool_call.arguments,
            output={
                "result_summary": tool_call.result_summary,
                "observed_market_price": market_price,
                "previous_market_price": prior_price,
                "shock_type": shock_type,
                "shock_multiplier": shock_multiplier,
                "shock_headline": shock_headline,
            },
            metadata={
                "run_id": run_id,
                "phase": phase.value,
                "round": round_number,
                "agent_id": agent_id,
                "negotiation_id": negotiation_id,
            },
            status_message=tool_call.result_summary,
        ):
            pass
        event_collector.log(
            event_type=RunEventType.TOOL_CALL,
            timestamp=tool_call.created_at,
            phase=phase,
            round_number=round_number,
            agent=agent_id,
            action=tool_call.tool_name,
            status=status,
            note=tool_call.result_summary,
            negotiation_id=negotiation_id,
            tool_name=tool_call.tool_name,
            observed_market_price=market_price,
            previous_market_price=prior_price,
            shock_type=shock_type,
            shock_multiplier=shock_multiplier,
            shock_headline=shock_headline,
        )
        if tool_call.tool_name == "check_market_price":
            event_collector.log(
                event_type=RunEventType.MARKET_PRICE_CHECK,
                timestamp=tool_call.created_at,
                phase=phase,
                round_number=round_number,
                agent=agent_id,
                status=status,
                note=tool_call.result_summary,
                negotiation_id=negotiation_id,
                tool_name=tool_call.tool_name,
                observed_market_price=market_price,
                previous_market_price=prior_price,
                shock_type=shock_type,
                shock_multiplier=shock_multiplier,
                shock_headline=shock_headline,
            )
            if shock_type and prior_price is not None and market_price is not None:
                event_collector.log(
                    event_type=RunEventType.MARKET_SHOCK,
                    timestamp=tool_call.created_at,
                    phase=phase,
                    round_number=round_number,
                    agent=agent_id,
                    status=status,
                    note=shock_headline or tool_call.result_summary,
                    reasoning_summary=str(tool_call.arguments.get("disruption_note"))
                    if tool_call.arguments.get("disruption_note") is not None
                    else tool_call.result_summary,
                    negotiation_id=negotiation_id,
                    tool_name=tool_call.tool_name,
                    observed_market_price=market_price,
                    previous_market_price=prior_price,
                    shock_type=shock_type,
                    shock_multiplier=shock_multiplier,
                    shock_headline=shock_headline,
                )


def _log_offer_received_event(
    event_collector: RunEventCollector,
    *,
    phase: PhaseName,
    round_number: int,
    negotiation_id: str,
    delivered_message: dict | None,
    recipient_agent_id: str,
    status: str,
) -> None:
    if not delivered_message or delivered_message.get("type") != "offer":
        return

    event_collector.log(
        event_type=RunEventType.OFFER_RECEIVED,
        phase=phase,
        round_number=round_number,
        agent=recipient_agent_id,
        offer_price=_coerce_price(delivered_message.get("price")),
        action=delivered_message.get("type"),
        status=status,
        note=delivered_message.get("note"),
        negotiation_id=negotiation_id,
    )


def _simulate_negotiation(
    phase: PhaseName,
    label: str,
    product_name: str,
    reference_market_price: float,
    openai_wrapper: OpenAIClientWrapper,
    langfuse_wrapper: LangfuseTraceWrapper,
    run_id: str,
    event_collector: RunEventCollector,
    seller: Agent,
    buyer: Agent,
    min_sell_price: float,
    max_buy_price: float,
    quantity: int,
    max_rounds: int,
    step_index_start: int,
    dependency_note: str,
    on_step=None,
) -> NegotiationSimulationResult:
    negotiation_id = f"neg-{uuid4().hex[:8]}"
    steps: list[NegotiationStep] = []
    step_index = step_index_start
    status = NegotiationStatus.OPEN
    final_price: float | None = None
    delivered_message: dict | None = None
    seller_last_offer: float | None = None
    buyer_last_offer: float | None = None
    rounds_completed = 0
    max_turns = min(max_rounds * 2, MAX_AGENT_TURNS_PER_NEGOTIATION)

    for turn_index in range(max_turns):
        round_number = (turn_index // 2) + 1
        rounds_completed = round_number
        turn_number = turn_index + 1
        current_agent = seller if turn_index % 2 == 0 else buyer
        shock_alert_message = None
        if get_shock_registry().has_pending(run_id):
            shock_alert_message = (
                "BREAKING: Market disruption detected. "
                "Call check_market_price immediately to get the updated reference price before making your next move."
            )
            steps.append(
                NegotiationStep(
                    index=step_index,
                    phase=phase,
                    negotiation_id=negotiation_id,
                    round_number=round_number,
                    agent_id="market_desk",
                    kind="system_notice",
                    message=shock_alert_message,
                    outcome="Operator queued a market disruption. Fresh market context is required.",
                    proposed_price=None,
                    delivered_message=None,
                    created_at=utc_now(),
                    tool_calls=[],
                )
            )
            if on_step is not None:
                on_step(steps)
            step_index += 1
        _log_offer_received_event(
            event_collector,
            phase=phase,
            round_number=round_number,
            negotiation_id=negotiation_id,
            delivered_message=delivered_message,
            recipient_agent_id=current_agent.id,
            status=status.value,
        )
        market_check = _market_check_event(
            run_id=run_id,
            agent_id=current_agent.id,
            step_index=step_index,
            negotiation_id=negotiation_id,
            product_name=product_name,
            reference_market_price=reference_market_price,
            role=current_agent.role,
            round_number=round_number,
        )
        tool_calls = [
            _review_state_event(
                agent_id=current_agent.id,
                step_index=step_index,
                phase=phase,
                negotiation_id=negotiation_id,
                round_number=round_number,
                delivered_message=delivered_message,
            ),
            market_check,
        ]
        _log_tool_events(
            event_collector=event_collector,
            langfuse_wrapper=langfuse_wrapper,
            run_id=run_id,
            phase=phase,
            round_number=round_number,
            negotiation_id=negotiation_id,
            agent_id=current_agent.id,
            tool_calls=tool_calls,
            status=status.value,
        )

        action = _decide_agent_action(
            openai_wrapper=openai_wrapper,
            langfuse_wrapper=langfuse_wrapper,
            run_id=run_id,
            phase=phase,
            negotiation_id=negotiation_id,
            agent=current_agent,
            seller=seller,
            buyer=buyer,
            delivered_message=delivered_message,
            min_sell_price=min_sell_price,
            max_buy_price=max_buy_price,
            seller_last_offer=seller_last_offer,
            buyer_last_offer=buyer_last_offer,
            round_number=round_number,
            max_rounds=max_rounds,
            turn_number=turn_number,
            max_turns=max_turns,
            latest_market_price=_coerce_price(market_check.arguments.get("observed_market_price")),
            latest_market_note=str(market_check.result_summary),
            latest_market_shock_note=(
                str(market_check.arguments.get("disruption_note"))
                if market_check.arguments.get("disruption_note") is not None
                else None
            ),
            operator_alert=shock_alert_message,
        )

        kind = action["action"]
        note = action.get("note", "").strip()
        reason = action.get("reason", "").strip()
        proposed_price = _coerce_price(action.get("price"))
        reservation_diagnostic = _reservation_diagnostic(
            agent=current_agent,
            is_seller=current_agent.id == seller.id,
            action=kind,
            proposed_price=proposed_price,
            delivered_message=delivered_message,
        )
        public_message = _compose_public_message(
            note=note,
            fallback=f"{current_agent.name} evaluated the current state.",
        )
        private_reasoning = _compose_private_reasoning(
            reason=reason,
            reservation_diagnostic=reservation_diagnostic,
        )
        now = utc_now()
        event_collector.log(
            event_type=RunEventType.AGENT_TURN,
            timestamp=now,
            phase=phase,
            round_number=round_number,
            agent=current_agent.id,
            action=kind,
            status=status.value,
            offer_price=proposed_price,
            note=public_message,
            reasoning_summary=private_reasoning,
            negotiation_id=negotiation_id,
        )

        if kind == "make_offer":
            if current_agent.id == seller.id:
                proposed_price = _offer_price_or_anchor(
                    proposed_price=proposed_price,
                    min_sell_price=min_sell_price,
                    max_buy_price=max_buy_price,
                    previous_offer=seller_last_offer,
                    counterparty_offer=buyer_last_offer,
                )
                seller_last_offer = proposed_price
            else:
                proposed_price = _offer_price_or_anchor(
                    proposed_price=proposed_price,
                    min_sell_price=min_sell_price,
                    max_buy_price=max_buy_price,
                    previous_offer=buyer_last_offer,
                    counterparty_offer=seller_last_offer,
                )
                buyer_last_offer = proposed_price

            message = _compose_public_message(
                note=note,
                fallback=f"{current_agent.name} proposes {proposed_price:.2f} per unit.",
            )
            outcome = "Offer queued for delivery on the next turn."
            if reservation_diagnostic:
                outcome = f"{outcome} {reservation_diagnostic}"
            steps.append(
                NegotiationStep(
                    index=step_index,
                    phase=phase,
                    negotiation_id=negotiation_id,
                    round_number=round_number,
                    agent_id=current_agent.id,
                    kind="offer",
                    message=message,
                    outcome=outcome,
                    proposed_price=proposed_price,
                    delivered_message=delivered_message,
                    created_at=now,
                    tool_calls=tool_calls,
                )
            )
            if on_step is not None:
                on_step(steps)
            delivered_message = {
                "type": "offer",
                "price": proposed_price,
                "note": message,
                "from_agent_id": current_agent.id,
            }
            event_collector.log(
                event_type=RunEventType.OFFER_MADE,
                timestamp=now,
                phase=phase,
                round_number=round_number,
                agent=current_agent.id,
                offer_price=proposed_price,
                action=kind,
                status=status.value,
                note=message,
                reasoning_summary=private_reasoning,
                negotiation_id=negotiation_id,
            )
            step_index += 1
        elif kind == "accept_offer" and delivered_message and delivered_message.get("type") == "offer":
            final_price = float(delivered_message["price"])
            steps.append(
                NegotiationStep(
                    index=step_index,
                    phase=phase,
                    negotiation_id=negotiation_id,
                    round_number=round_number,
                    agent_id=current_agent.id,
                    kind="accept",
                    message=_compose_public_message(
                        note=note,
                        fallback=f"{current_agent.name} accepts the pending offer.",
                    ),
                    outcome=(
                        "Negotiation ends with an accepted deal."
                        + (f" {reservation_diagnostic}" if reservation_diagnostic else "")
                    ),
                    proposed_price=final_price,
                    delivered_message=delivered_message,
                    created_at=now,
                    tool_calls=tool_calls,
                )
            )
            if on_step is not None:
                on_step(steps)
            status = NegotiationStatus.ACCEPTED
            event_collector.log(
                event_type=RunEventType.ACCEPT,
                timestamp=now,
                phase=phase,
                round_number=round_number,
                agent=current_agent.id,
                offer_price=final_price,
                action=kind,
                status=status.value,
                note=_compose_public_message(
                    note=note,
                    fallback=f"{current_agent.name} accepts the pending offer.",
                ),
                reasoning_summary=private_reasoning,
                negotiation_id=negotiation_id,
            )
            step_index += 1
            break
        elif kind == "reject_offer":
            steps.append(
                NegotiationStep(
                    index=step_index,
                    phase=phase,
                    negotiation_id=negotiation_id,
                    round_number=round_number,
                    agent_id=current_agent.id,
                    kind="reject",
                    message=_compose_public_message(
                        note=note,
                        fallback=f"{current_agent.name} rejects the pending offer.",
                    ),
                    outcome=(
                        "Negotiation ends with a rejection."
                        + (f" {reservation_diagnostic}" if reservation_diagnostic else "")
                    ),
                    proposed_price=delivered_message.get("price") if delivered_message else None,
                    delivered_message=delivered_message,
                    created_at=now,
                    tool_calls=tool_calls,
                )
            )
            if on_step is not None:
                on_step(steps)
            status = NegotiationStatus.REJECTED
            event_collector.log(
                event_type=RunEventType.REJECT,
                timestamp=now,
                phase=phase,
                round_number=round_number,
                agent=current_agent.id,
                offer_price=_coerce_price(delivered_message.get("price")) if delivered_message else None,
                action=kind,
                status=status.value,
                note=_compose_public_message(
                    note=note,
                    fallback=f"{current_agent.name} rejects the pending offer.",
                ),
                reasoning_summary=private_reasoning,
                negotiation_id=negotiation_id,
            )
            step_index += 1
            break
        else:
            fallback_price = _offer_price_or_anchor(
                proposed_price=None,
                min_sell_price=min_sell_price,
                max_buy_price=max_buy_price,
                previous_offer=(
                    seller_last_offer if current_agent.id == seller.id else buyer_last_offer
                ),
                counterparty_offer=(
                    buyer_last_offer if current_agent.id == seller.id else seller_last_offer
                ),
            )
            if current_agent.id == seller.id:
                seller_last_offer = fallback_price
            else:
                buyer_last_offer = fallback_price

            message = _compose_public_message(
                note=note,
                fallback=f"{current_agent.name} submits {fallback_price:.2f} per unit.",
            )
            steps.append(
                NegotiationStep(
                    index=step_index,
                    phase=phase,
                    negotiation_id=negotiation_id,
                    round_number=round_number,
                    agent_id=current_agent.id,
                    kind="offer",
                    message=message,
                    outcome="Fallback offer queued for delivery on the next turn.",
                    proposed_price=fallback_price,
                    delivered_message=delivered_message,
                    created_at=now,
                    tool_calls=tool_calls,
                )
            )
            if on_step is not None:
                on_step(steps)
            delivered_message = {
                "type": "offer",
                "price": fallback_price,
                "note": message,
                "from_agent_id": current_agent.id,
            }
            event_collector.log(
                event_type=RunEventType.OFFER_MADE,
                timestamp=now,
                phase=phase,
                round_number=round_number,
                agent=current_agent.id,
                offer_price=fallback_price,
                action="make_offer",
                status=status.value,
                note=message,
                reasoning_summary="\n".join(
                    value
                    for value in [
                        "Fallback offer was used because the decision payload was incomplete.",
                        reservation_diagnostic,
                    ]
                    if value
                ),
                negotiation_id=negotiation_id,
            )
            step_index += 1

    if status == NegotiationStatus.OPEN:
        timeout_timestamp = utc_now()
        status = NegotiationStatus.TIMEOUT
        steps.append(
            NegotiationStep(
                index=step_index,
                phase=phase,
                negotiation_id=negotiation_id,
                round_number=rounds_completed,
                agent_id=buyer.id,
                kind="timeout",
                message=f"{label} reached the turn limit without agreement.",
                outcome="Negotiation times out.",
                proposed_price=None,
                delivered_message=delivered_message,
                created_at=timeout_timestamp,
            )
        )
        if on_step is not None:
            on_step(steps)
        event_collector.log(
            event_type=RunEventType.TIMEOUT,
            timestamp=timeout_timestamp,
            phase=phase,
            round_number=rounds_completed,
            agent=buyer.id,
            action="timeout",
            status=status.value,
            note=f"{label} reached the turn limit without agreement.",
            reasoning_summary="Negotiation timed out after exhausting the configured turn limit.",
            negotiation_id=negotiation_id,
        )

    opening_seller_offer = next(
        (step.proposed_price for step in steps if step.agent_id == seller.id and step.proposed_price is not None),
        min_sell_price,
    )
    opening_buyer_offer = next(
        (step.proposed_price for step in steps if step.agent_id == buyer.id and step.proposed_price is not None),
        max_buy_price,
    )

    return NegotiationSimulationResult(
        record=NegotiationRecord(
            id=negotiation_id,
            phase=phase,
            label=label,
            seller_agent_id=seller.id,
            buyer_agent_id=buyer.id,
            status=status,
            max_rounds=max_rounds,
            quantity=quantity,
            rounds_completed=rounds_completed,
            opening_seller_offer=round(opening_seller_offer, 2),
            opening_buyer_offer=round(opening_buyer_offer, 2),
            final_price=final_price,
            outcome_summary=_build_outcome_summary(
                label=label,
                status=status,
                final_price=final_price,
            ),
            dependency_note=dependency_note,
        ),
        steps=steps,
    )


def _build_phases() -> list[Phase]:
    return [
        Phase(
            name=PhaseName.SUPPLIER_MANUFACTURER,
            label="Supplier to Manufacturer",
            order=1,
            description="The supplier negotiates an upstream unit price with the manufacturer.",
        ),
        Phase(
            name=PhaseName.MANUFACTURER_RETAILER,
            label="Manufacturer to Retailer",
            order=2,
            description="The manufacturer negotiates a downstream unit price with the retailer after the upstream deal sets its cost basis.",
        ),
    ]


def _resolve_run_status(negotiations: list[NegotiationRecord]) -> RunStatus:
    if len(negotiations) == 2 and all(
        negotiation.status == NegotiationStatus.ACCEPTED
        for negotiation in negotiations
    ):
        return RunStatus.COMPLETED
    if any(negotiation.status == NegotiationStatus.OPEN for negotiation in negotiations):
        return RunStatus.RUNNING
    return RunStatus.FAILED


def _build_diagnosis(
    first_negotiation: NegotiationRecord,
    second_negotiation: NegotiationRecord | None,
    manufacturer_sell_floor: float | None,
    manufacturer_cost_basis: float | None,
    currency: str,
) -> DiagnosisSummary:
    first_outcome = (
        f"Upstream deal {first_negotiation.status.value}"
        + (
            f" at {first_negotiation.final_price:.2f} {currency}."
            if first_negotiation.final_price is not None
            else "."
        )
    )
    second_outcome = (
        (
            f"Downstream deal {second_negotiation.status.value}"
            + (
                f" at {second_negotiation.final_price:.2f} {currency}."
                if second_negotiation.final_price is not None
                else "."
            )
        )
        if second_negotiation is not None
        else "Downstream negotiation did not run because the upstream deal did not close."
    )

    return DiagnosisSummary(
        outcome=f"{first_outcome} {second_outcome}",
        chain_effect=(
            (
                f"The manufacturer carried a cost basis of {manufacturer_cost_basis:.2f} {currency}, "
                f"which forced a downstream sell floor of {manufacturer_sell_floor:.2f} {currency}."
            )
            if manufacturer_cost_basis is not None and manufacturer_sell_floor is not None
            else "The upstream deal did not establish a downstream cost basis, so phase two was skipped."
        ),
        key_risks=[
            "A costly upstream agreement compresses downstream negotiating room.",
            "Turn limits can force timeouts even when the gap is narrowing.",
        ],
        key_signals=[
            f"Supplier-manufacturer status: {first_negotiation.status.value}.",
            (
                f"Manufacturer-retailer status: {second_negotiation.status.value}."
                if second_negotiation is not None
                else "Manufacturer-retailer status: not run."
            ),
        ],
        suggested_next_actions=[
            "Tune reservation prices and turn limits to test sensitivity.",
            "Add richer quantity or margin tradeoffs before introducing LLM behavior.",
        ],
    )


def _build_export_summary_payload(
    run: RunRecord,
    event_log: RunEventLog,
    trace_id: str | None,
    trace_url: str | None,
) -> dict:
    derived = _build_derived_export_fields(run=run, event_log=event_log)
    return {
        "run_id": run.id,
        "title": run.title,
        "status": run.status,
        "trace_id": trace_id,
        "trace_url": trace_url,
        "scenario": run.scenario,
        "run": run.model_dump(mode="json"),
        "negotiations": [negotiation.model_dump(mode="json") for negotiation in run.negotiations],
        "diagnosis": run.diagnosis.model_dump(mode="json"),
        "derived": derived,
    }


def _build_trace_export_payload(
    run: RunRecord,
    trace_id: str | None,
    trace_url: str | None,
    langfuse_status: str,
    langfuse_available: bool,
    langfuse_configured: bool,
) -> dict:
    return {
        "run_id": run.id,
        "trace_id": trace_id,
        "trace_url": trace_url,
        "langfuse_status": langfuse_status,
        "langfuse_available": langfuse_available,
        "langfuse_configured": langfuse_configured,
        "trace_available": bool(trace_id),
        "status": run.status,
        "phase_statuses": [
            {
                "phase": negotiation.phase.value,
                "status": negotiation.status.value,
                "rounds_completed": negotiation.rounds_completed,
                "final_price": negotiation.final_price,
            }
            for negotiation in run.negotiations
        ],
    }


def _build_conversation_export_payload(run: RunRecord) -> dict:
    agent_map = {agent.id: agent for agent in run.agents}
    messages = []
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
                "timestamp": step.created_at.isoformat(),
                "phase": step.phase.value,
                "round": step.round_number,
                "speaker_id": step.agent_id,
                "speaker_name": speaker_name,
                "speaker_role": agent.role.value if agent is not None else None,
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

    return {
        "run_id": run.id,
        "title": run.title,
        "status": run.status.value,
        "messages": messages,
    }


def _build_derived_export_fields(run: RunRecord, event_log: RunEventLog) -> dict:
    first_negotiation = run.negotiations[0] if run.negotiations else None
    second_negotiation = run.negotiations[1] if len(run.negotiations) > 1 else None
    manufacturer_margin_after_first_deal = None
    if first_negotiation and first_negotiation.final_price is not None:
        if second_negotiation and second_negotiation.final_price is not None:
            manufacturer_margin_after_first_deal = round(
                second_negotiation.final_price - first_negotiation.final_price,
                2,
            )
        else:
            manufacturer = next(
                (agent for agent in run.agents if agent.role == AgentRole.MANUFACTURER),
                None,
            )
            if (
                manufacturer is not None
                and manufacturer.reservation_prices.min_sell_price is not None
            ):
                manufacturer_margin_after_first_deal = round(
                    manufacturer.reservation_prices.min_sell_price - first_negotiation.final_price,
                    2,
                )

    belief_gap_samples = [
        {
            "timestamp": event.timestamp.isoformat(),
            "phase": event.phase.value if event.phase is not None else None,
            "round": event.round,
            "agent": event.agent,
            "observed_market_price": event.observed_market_price,
            "true_market_price": run.product_context.baseline_unit_price,
            "belief_gap": round(
                event.observed_market_price - run.product_context.baseline_unit_price,
                2,
            ),
        }
        for event in event_log.events
        if event.event_type == RunEventType.MARKET_PRICE_CHECK
        and event.observed_market_price is not None
    ]
    average_belief_gap = None
    if belief_gap_samples:
        average_belief_gap = round(
            sum(sample["belief_gap"] for sample in belief_gap_samples) / len(belief_gap_samples),
            2,
        )
    reservation_price_violations = [
        {
            "timestamp": event.timestamp.isoformat(),
            "phase": event.phase.value if event.phase is not None else None,
            "round": event.round,
            "agent": event.agent,
            "action": event.action,
            "offer_price": event.offer_price,
            "detail": event.reasoning_summary,
        }
        for event in event_log.events
        if event.reasoning_summary and "reservation-price violation" in event.reasoning_summary.lower()
    ]

    failure_point = _infer_failure_point(run=run, event_log=event_log)
    failure_type = _infer_failure_type(run=run, event_log=event_log)

    return {
        "true_market_price": run.product_context.baseline_unit_price,
        "belief_gap_samples": belief_gap_samples,
        "average_belief_gap": average_belief_gap,
        "manufacturer_margin_after_first_deal": manufacturer_margin_after_first_deal,
        "reservation_price_violations": reservation_price_violations,
        "reservation_price_violation_count": len(reservation_price_violations),
        "where_run_failed": failure_point,
        "suspected_failure_type": failure_type,
    }


def _infer_failure_point(run: RunRecord, event_log: RunEventLog) -> dict | None:
    if run.status == RunStatus.COMPLETED:
        return None

    final_event = next(
        (event for event in reversed(event_log.events) if event.event_type == RunEventType.FINAL_OUTCOME),
        None,
    )
    if final_event and final_event.phase is not None:
        return {
            "phase": final_event.phase.value,
            "round": final_event.round,
            "agent": final_event.agent,
            "note": final_event.note,
        }

    failed_negotiation = next(
        (negotiation for negotiation in run.negotiations if negotiation.status != NegotiationStatus.ACCEPTED),
        None,
    )
    if failed_negotiation is None:
        return None

    return {
        "phase": failed_negotiation.phase.value,
        "round": failed_negotiation.rounds_completed,
        "agent": failed_negotiation.buyer_agent_id,
        "note": failed_negotiation.outcome_summary,
    }


def _infer_failure_type(run: RunRecord, event_log: RunEventLog) -> str | None:
    if run.status == RunStatus.COMPLETED:
        return None

    final_event = next(
        (event for event in reversed(event_log.events) if event.event_type == RunEventType.FINAL_OUTCOME),
        None,
    )
    note = (final_event.note if final_event else "") or ""
    lowered = note.lower()

    if "invalid_api_key" in lowered or "incorrect api key" in lowered or "401" in lowered:
        return "authentication_error"
    if "openai" in lowered and "failed" in lowered:
        return "llm_call_failure"
    if "invalid json" in lowered:
        return "llm_output_parse_error"
    if any(negotiation.status == NegotiationStatus.TIMEOUT for negotiation in run.negotiations):
        return "negotiation_timeout"
    if any(negotiation.status == NegotiationStatus.REJECTED for negotiation in run.negotiations):
        return "negotiation_rejected"

    return "unknown_failure"


def _build_outcome_summary(
    label: str,
    status: NegotiationStatus,
    final_price: float | None,
) -> str:
    if status == NegotiationStatus.ACCEPTED and final_price is not None:
        return f"{label} accepted at {final_price:.2f}."
    if status == NegotiationStatus.REJECTED:
        return f"{label} ended in rejection."
    if status == NegotiationStatus.TIMEOUT:
        return f"{label} reached the turn limit without agreement."
    return f"{label} remains open."


def _decide_agent_action(
    openai_wrapper: OpenAIClientWrapper,
    langfuse_wrapper: LangfuseTraceWrapper,
    run_id: str,
    phase: PhaseName,
    negotiation_id: str,
    agent: Agent,
    seller: Agent,
    buyer: Agent,
    delivered_message: dict | None,
    min_sell_price: float,
    max_buy_price: float,
    seller_last_offer: float | None,
    buyer_last_offer: float | None,
    round_number: int,
    max_rounds: int,
    turn_number: int,
    max_turns: int,
    latest_market_price: float | None,
    latest_market_note: str | None,
    latest_market_shock_note: str | None,
    operator_alert: str | None,
) -> dict:
    prompt = _build_agent_prompt(
        agent=agent,
        seller=seller,
        buyer=buyer,
        delivered_message=delivered_message,
        min_sell_price=min_sell_price,
        max_buy_price=max_buy_price,
        seller_last_offer=seller_last_offer,
        buyer_last_offer=buyer_last_offer,
        round_number=round_number,
        max_rounds=max_rounds,
        turn_number=turn_number,
        max_turns=max_turns,
        latest_market_price=latest_market_price,
        latest_market_note=latest_market_note,
        latest_market_shock_note=latest_market_shock_note,
        operator_alert=operator_alert,
    )
    with langfuse_wrapper.start_span(
        name="agent-decision",
        input={
            "agent_id": agent.id,
            "role": agent.role.value,
            "round_number": round_number,
            "turn_number": turn_number,
            "max_rounds": max_rounds,
            "max_turns": max_turns,
            "delivered_message": delivered_message,
            "visible_last_seller_offer": seller_last_offer,
            "visible_last_buyer_offer": buyer_last_offer,
            "seller_floor": min_sell_price,
            "buyer_ceiling": max_buy_price,
            "latest_market_price": latest_market_price,
            "latest_market_note": latest_market_note,
            "latest_market_shock_note": latest_market_shock_note,
            "operator_alert": operator_alert,
        },
        metadata={
            "run_id": run_id,
            "phase": phase.value,
            "negotiation_id": negotiation_id,
            "agent_id": agent.id,
        },
        status_message="Agent decision started.",
    ) as decision_span:
        try:
            decision = openai_wrapper.decide_action(
                prompt,
                metadata={
                    "run_id": run_id,
                    "phase": phase.value,
                    "negotiation_id": negotiation_id,
                    "agent_id": agent.id,
                    "round_number": round_number,
                    "turn_number": turn_number,
                },
                langfuse_wrapper=langfuse_wrapper,
            )
        except OpenAIDecisionError as exc:
            decision_span.update(
                output={"error": str(exc)},
                status_message=str(exc),
                level="ERROR",
            )
            raise SimulationExecutionError(str(exc)) from exc

        if _is_valid_action(decision):
            decision_span.update(
                output=decision,
                status_message="Agent decision completed.",
            )
            return decision

        decision_span.update(
            output=decision,
            status_message="OpenAI returned an unsupported action.",
            level="ERROR",
        )
        raise SimulationExecutionError("OpenAI returned an unsupported action.")


def _build_agent_prompt(
    agent: Agent,
    seller: Agent,
    buyer: Agent,
    delivered_message: dict | None,
    min_sell_price: float,
    max_buy_price: float,
    seller_last_offer: float | None,
    buyer_last_offer: float | None,
    round_number: int,
    max_rounds: int,
    turn_number: int,
    max_turns: int,
    latest_market_price: float | None,
    latest_market_note: str | None,
    latest_market_shock_note: str | None,
    operator_alert: str | None,
) -> str:
    visible_state = {
        "agent_id": agent.id,
        "role": agent.role.value,
        "objective": agent.objective,
        "reservation_prices": agent.reservation_prices.model_dump(mode="json"),
        "visible_last_seller_offer": seller_last_offer,
        "visible_last_buyer_offer": buyer_last_offer,
        "delivered_message": delivered_message,
        "round_number": round_number,
        "turn_number": turn_number,
        "max_rounds": max_rounds,
        "max_turns": max_turns,
        "seller_id": seller.id,
        "buyer_id": buyer.id,
        "latest_market_context": {
            "observed_price": latest_market_price,
            "tool_summary": latest_market_note,
            "disruption_note": latest_market_shock_note,
        },
        "operator_alert": operator_alert,
        "rules": [
            "Choose exactly one action.",
            "Actions: make_offer, accept_offer, reject_offer.",
            "Accept or reject only if you received an offer.",
            "Your reservation prices are private to you. Other agents do not know them.",
            "Treat your reservation prices as private reference points, not hard-coded cutoffs.",
            "You may continue negotiating even after seeing an unattractive offer if that seems strategically useful.",
            "Reject only if you intentionally want to end the negotiation now.",
            "Do not assume the market reference seen by other agents matches yours.",
            "Write natural negotiation dialogue, not fragments.",
            "Use note as the short counterparty-facing message that will be delivered to the other agent.",
            "Keep note to 1 or 2 concise sentences.",
            "Use reason as your private thinking for the trace and UI.",
            "Use 2 to 4 sentences for reason unless the deal is obviously over.",
            "Put price logic, constraints, and concession strategy in reason, not note.",
            f"Do not exceed {max_turns} total agent turns in this negotiation.",
            "Return JSON only.",
        ],
    }
    return (
        "You are a negotiation agent in a realistic business conversation. Decide one action.\n"
        "Return JSON with keys action, price, note, reason.\n"
        "Your reservation prices are hidden from the counterparty and are internal reference points, not rigid rules.\n"
        "Make the move that seems reasonable from your local perspective; imperfect judgment, bluffing, patience, and misreads are allowed.\n"
        "Use the latest market-check result and any operator alert before choosing your next move.\n"
        "The other agent will only see note. Keep it short, direct, and suitable to send externally.\n"
        "Only you and the observability layer will see reason. Put your fuller internal rationale there.\n"
        "If action is make_offer, include price and a short external note.\n"
        "If action is accept_offer, price can be null.\n"
        "If action is reject_offer, include a short external note and a clear private reason.\n"
        "Do not end the negotiation early unless you actually want to walk away.\n"
        f"{json.dumps(visible_state)}"
    )


def _offer_price_or_anchor(
    proposed_price: float | None,
    min_sell_price: float,
    max_buy_price: float,
    previous_offer: float | None,
    counterparty_offer: float | None,
) -> float:
    if proposed_price is None:
        anchor = (
            previous_offer
            if previous_offer is not None
            else counterparty_offer
            if counterparty_offer is not None
            else round((min_sell_price + max_buy_price) / 2, 2)
        )
        return round(anchor, 2)

    return round(proposed_price, 2)


def _review_state_event(
    agent_id: str,
    step_index: int,
    phase: PhaseName,
    negotiation_id: str,
    round_number: int,
    delivered_message: dict | None,
) -> ToolCallEvent:
    summary = (
        f"Reviewed state for {phase.value} round {round_number}. "
        f"Pending message: {delivered_message if delivered_message else 'none'}."
    )
    return ToolCallEvent(
        id=f"tool-{uuid4().hex[:8]}",
        step_index=step_index,
        agent_id=agent_id,
        tool_name="review_state",
        arguments={
            "negotiation_id": negotiation_id,
            "round_number": round_number,
        },
        result_summary=summary,
        created_at=utc_now(),
    )


def _market_check_event(
    run_id: str,
    agent_id: str,
    step_index: int,
    negotiation_id: str,
    product_name: str,
    reference_market_price: float,
    role: AgentRole,
    round_number: int,
) -> ToolCallEvent:
    observed_price = _agent_market_price(
        reference_market_price=reference_market_price,
        role=role,
        round_number=round_number,
    )
    shock = get_shock_registry().consume(run_id)
    shocked_price = observed_price
    disruption_note = None
    arguments: dict[str, str | int | float | bool | None] = {
        "run_id": run_id,
        "negotiation_id": negotiation_id,
        "product": product_name,
        "observed_market_price": observed_price,
    }
    result_summary = f"Observed market reference price: {observed_price:.2f}."

    if shock is not None:
        shocked_price = round(observed_price * shock.multiplier, 2)
        disruption_note = (
            f"{shock.headline} Reference price moved from {observed_price:.2f} to {shocked_price:.2f}."
        )
        arguments = {
            **arguments,
            "base_market_price": observed_price,
            "observed_market_price": shocked_price,
            "shock_type": shock.shock_type,
            "shock_multiplier": shock.multiplier,
            "shock_headline": shock.headline,
            "disruption_note": disruption_note,
        }
        result_summary = (
            f"Observed disrupted market reference price: {shocked_price:.2f}. {shock.headline}"
        )

    return ToolCallEvent(
        id=f"tool-{uuid4().hex[:8]}",
        step_index=step_index,
        agent_id=agent_id,
        tool_name="check_market_price",
        arguments=arguments,
        result_summary=result_summary,
        created_at=utc_now(),
    )


def _agent_market_price(
    reference_market_price: float,
    role: AgentRole,
    round_number: int,
) -> float:
    role_bias = {
        AgentRole.SUPPLIER: 0.18,
        AgentRole.MANUFACTURER: 0.05,
        AgentRole.RETAILER: -0.12,
    }[role]
    round_bias = ((round_number - 1) % 3 - 1) * 0.04
    return round(reference_market_price + role_bias + round_bias, 2)


def _coerce_price(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _is_valid_action(decision: dict) -> bool:
    return decision.get("action") in {"make_offer", "accept_offer", "reject_offer"}


def _build_seeded_requests(seed: int) -> list[SimulationRunConfig]:
    rng = Random(seed)
    return [
        _build_harvest_pressure_scenario(rng, seed, 1),
        _build_packaging_cost_scenario(rng, seed, 2),
        _build_retail_promotion_scenario(rng, seed, 3),
    ]


def _build_harvest_pressure_scenario(rng: Random, seed: int, index: int):
    target_quantity = rng.randint(1800, 2600)
    baseline_unit_price = round(rng.uniform(2.1, 2.9), 2)
    supplier_min_sell_price = round(baseline_unit_price * rng.uniform(0.86, 0.94), 2)
    manufacturer_max_buy_price = round(baseline_unit_price * rng.uniform(0.98, 1.08), 2)
    manufacturer_margin_floor = round(rng.uniform(0.25, 0.42), 2)
    manufacturer_min_sell_price = round(manufacturer_max_buy_price + manufacturer_margin_floor, 2)
    retailer_max_buy_price = round(manufacturer_min_sell_price * rng.uniform(1.06, 1.18), 2)
    return _seeded_request(
        seed=seed,
        index=index,
        title="Tomato Harvest Pricing Run",
        market_region=_pick(rng, ["California", "Texas", "Ontario"]),
        demand_signal="Retail ketchup demand is steady, but wholesale buyers want price protection before peak tomato procurement.",
        supply_signal="Tomato harvest yields are uneven across growing regions, putting pressure on paste input pricing.",
        baseline_unit_price=baseline_unit_price,
        target_quantity=target_quantity,
        supplier_min_sell_price=supplier_min_sell_price,
        manufacturer_max_buy_price=manufacturer_max_buy_price,
        manufacturer_min_sell_price=manufacturer_min_sell_price,
        retailer_max_buy_price=retailer_max_buy_price,
        manufacturer_margin_floor=manufacturer_margin_floor,
        max_rounds=rng.randint(5, 7),
    )


def _build_packaging_cost_scenario(rng: Random, seed: int, index: int):
    target_quantity = rng.randint(1400, 2200)
    baseline_unit_price = round(rng.uniform(2.4, 3.2), 2)
    supplier_min_sell_price = round(baseline_unit_price * rng.uniform(0.88, 0.96), 2)
    manufacturer_max_buy_price = round(baseline_unit_price * rng.uniform(1.0, 1.09), 2)
    manufacturer_margin_floor = round(rng.uniform(0.3, 0.5), 2)
    manufacturer_min_sell_price = round(manufacturer_max_buy_price + manufacturer_margin_floor, 2)
    retailer_max_buy_price = round(manufacturer_min_sell_price * rng.uniform(1.05, 1.16), 2)
    return _seeded_request(
        seed=seed,
        index=index,
        title="Bottle and Cap Cost Run",
        market_region=_pick(rng, ["Midwest", "Southeast", "Northeast"]),
        demand_signal="Retailers are asking for stable ketchup pricing even as packaging contracts are being repriced.",
        supply_signal="Glass bottle and cap suppliers increased quoting pressure after freight and packaging resin costs moved up.",
        baseline_unit_price=baseline_unit_price,
        target_quantity=target_quantity,
        supplier_min_sell_price=supplier_min_sell_price,
        manufacturer_max_buy_price=manufacturer_max_buy_price,
        manufacturer_min_sell_price=manufacturer_min_sell_price,
        retailer_max_buy_price=retailer_max_buy_price,
        manufacturer_margin_floor=manufacturer_margin_floor,
        max_rounds=rng.randint(4, 6),
    )


def _build_retail_promotion_scenario(rng: Random, seed: int, index: int):
    target_quantity = rng.randint(2200, 3200)
    baseline_unit_price = round(rng.uniform(2.6, 3.4), 2)
    supplier_min_sell_price = round(baseline_unit_price * rng.uniform(0.9, 0.97), 2)
    manufacturer_max_buy_price = round(baseline_unit_price * rng.uniform(1.02, 1.11), 2)
    manufacturer_margin_floor = round(rng.uniform(0.28, 0.48), 2)
    manufacturer_min_sell_price = round(manufacturer_max_buy_price + manufacturer_margin_floor, 2)
    retailer_max_buy_price = round(manufacturer_min_sell_price * rng.uniform(1.04, 1.14), 2)
    return _seeded_request(
        seed=seed,
        index=index,
        title="Promotion Inventory Surge Run",
        market_region=_pick(rng, ["West Coast", "Great Lakes", "Mid-Atlantic"]),
        demand_signal="Retail chains are loading ketchup inventory ahead of a multi-week promotion and need fast replenishment.",
        supply_signal="Upstream ingredient supply is stable, but rush production slots are limited this month.",
        baseline_unit_price=baseline_unit_price,
        target_quantity=target_quantity,
        supplier_min_sell_price=supplier_min_sell_price,
        manufacturer_max_buy_price=manufacturer_max_buy_price,
        manufacturer_min_sell_price=manufacturer_min_sell_price,
        retailer_max_buy_price=retailer_max_buy_price,
        manufacturer_margin_floor=manufacturer_margin_floor,
        max_rounds=rng.randint(4, 6),
    )


def _seeded_request(
    seed: int,
    index: int,
    title: str,
    market_region: str,
    demand_signal: str,
    supply_signal: str,
    baseline_unit_price: float,
    target_quantity: int,
    supplier_min_sell_price: float,
    manufacturer_max_buy_price: float,
    manufacturer_min_sell_price: float,
    retailer_max_buy_price: float,
    manufacturer_margin_floor: float,
    max_rounds: int,
):
    return SimulationRunConfig(
        title=f"{title} Seed {seed}-{index}",
        product_name="Tomato Ketchup",
        product_category="condiments",
        market_region=market_region,
        baseline_unit_price=baseline_unit_price,
        target_quantity=target_quantity,
        currency="USD",
        demand_signal=demand_signal,
        supply_signal=supply_signal,
        max_rounds_per_negotiation=max_rounds,
        supplier_min_sell_price=supplier_min_sell_price,
        manufacturer_max_buy_price=manufacturer_max_buy_price,
        manufacturer_min_sell_price=manufacturer_min_sell_price,
        retailer_max_buy_price=retailer_max_buy_price,
        manufacturer_margin_floor=manufacturer_margin_floor,
    )


def _pick(rng: Random, options: list[str]) -> str:
    return options[rng.randrange(len(options))]
