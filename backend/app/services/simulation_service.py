import json
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
    RunRecord,
    RunStatus,
    ToolCallEvent,
    utc_now,
)
from backend.app.models.simulation import (
    PipelineDependencyStatus,
    PipelineExportRecord,
    SimulationTestPipelineResult,
)
from backend.app.models.simulation_request import SimulationRunRequest
from backend.app.services.export_repository import save_simulation_export
from backend.app.services.run_repository import save_run_record


class SimulationExecutionError(Exception):
    pass


def simulate_run(request: SimulationRunRequest | None = None) -> RunRecord:
    if request is None:
        raise SimulationExecutionError("Simulation input is required.")

    simulation_request = request
    created_at = utc_now()
    settings = get_settings()
    openai_wrapper = OpenAIClientWrapper(settings)
    openai_configured, openai_available, openai_message = openai_wrapper.get_status()
    if not openai_configured or not openai_available:
        raise SimulationExecutionError(openai_message)

    run_id = f"run-{uuid4().hex[:10]}"
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

    first_result = _simulate_negotiation(
        openai_wrapper=openai_wrapper,
        phase=PhaseName.SUPPLIER_MANUFACTURER,
        label="Supplier to Manufacturer",
        product_name=simulation_request.product_name,
        seller=supplier,
        buyer=manufacturer,
        min_sell_price=simulation_request.supplier_min_sell_price,
        max_buy_price=simulation_request.manufacturer_max_buy_price,
        quantity=simulation_request.target_quantity,
        max_rounds=simulation_request.max_rounds_per_negotiation,
        step_index_start=1,
        dependency_note="Initial upstream procurement negotiation.",
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

        second_result = _simulate_negotiation(
            openai_wrapper=openai_wrapper,
            phase=PhaseName.MANUFACTURER_RETAILER,
            label="Manufacturer to Retailer",
            product_name=simulation_request.product_name,
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

    run = RunRecord(
        id=run_id,
        title=simulation_request.title,
        status=status,
        scenario=(
            f"{simulation_request.product_name} in {simulation_request.market_region}. "
            f"Supplier-to-manufacturer pricing sets the manufacturer cost basis before the retailer negotiation."
        ),
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
    return run


def run_test_pipeline(request: SimulationRunRequest | None = None) -> SimulationTestPipelineResult:
    settings = get_settings()
    openai_wrapper = OpenAIClientWrapper(settings)
    langfuse_wrapper = LangfuseTraceWrapper(settings)
    openai_configured, openai_available, openai_message = openai_wrapper.get_status()
    langfuse_configured, langfuse_available, langfuse_message = langfuse_wrapper.get_status()
    events: list[str] = []

    try:
        run = simulate_run(request)
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

    trace_id = langfuse_wrapper.create_trace_reference(run.id)
    if trace_id:
        events.append(f"Initialized trace {trace_id}.")
    else:
        events.append("Skipped trace initialization because Langfuse is unavailable.")

    export_path = save_simulation_export(
        exports_dir=settings.exports_dir,
        run_id=run.id,
        payload=_build_export_payload(run=run, trace_id=trace_id),
    )
    events.append(f"Saved simulation export to {export_path.name}.")

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
            file_path=str(export_path),
            created_at=run.updated_at,
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


def _simulate_negotiation(
    phase: PhaseName,
    label: str,
    product_name: str,
    openai_wrapper: OpenAIClientWrapper,
    seller: Agent,
    buyer: Agent,
    min_sell_price: float,
    max_buy_price: float,
    quantity: int,
    max_rounds: int,
    step_index_start: int,
    dependency_note: str,
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

    if max_buy_price < min_sell_price:
        now = utc_now()
        steps.append(
            NegotiationStep(
                index=step_index,
                phase=phase,
                negotiation_id=negotiation_id,
                round_number=1,
                agent_id=seller.id,
                kind="offer",
                proposed_price=min_sell_price,
                message=f"{seller.name} opens at {min_sell_price:.2f}.",
                outcome="Seller anchors at its minimum acceptable price.",
                created_at=now,
                tool_calls=[
                    _review_state_event(
                        agent_id=seller.id,
                        step_index=step_index,
                        phase=phase,
                        negotiation_id=negotiation_id,
                        round_number=1,
                        delivered_message=None,
                    ),
                    _market_check_event(
                        agent_id=seller.id,
                        step_index=step_index,
                        negotiation_id=negotiation_id,
                        product_name=product_name,
                        baseline_price=min_sell_price,
                        role=seller.role,
                        round_number=1,
                    ),
                ],
            )
        )
        step_index += 1
        steps.append(
            NegotiationStep(
                index=step_index,
                phase=phase,
                negotiation_id=negotiation_id,
                round_number=1,
                agent_id=buyer.id,
                kind="reject",
                proposed_price=max_buy_price,
                message=f"{buyer.name} rejects because its ceiling is {max_buy_price:.2f}.",
                outcome="Negotiation ends immediately due to non-overlapping reservation prices.",
                created_at=utc_now(),
                tool_calls=[
                    _review_state_event(
                        agent_id=buyer.id,
                        step_index=step_index,
                        phase=phase,
                        negotiation_id=negotiation_id,
                        round_number=1,
                        delivered_message={
                            "type": "offer",
                            "price": min_sell_price,
                            "note": f"{seller.name} opens at {min_sell_price:.2f}.",
                        },
                    ),
                    _market_check_event(
                        agent_id=buyer.id,
                        step_index=step_index,
                        negotiation_id=negotiation_id,
                        product_name=product_name,
                        baseline_price=max_buy_price,
                        role=buyer.role,
                        round_number=1,
                    ),
                ],
            )
        )
        return NegotiationSimulationResult(
            record=NegotiationRecord(
                id=negotiation_id,
                phase=phase,
                label=label,
                seller_agent_id=seller.id,
                buyer_agent_id=buyer.id,
                status=NegotiationStatus.REJECTED,
                max_rounds=max_rounds,
                quantity=quantity,
                rounds_completed=1,
                opening_seller_offer=min_sell_price,
                opening_buyer_offer=max_buy_price,
                outcome_summary="Negotiation rejected immediately because reservation prices did not overlap.",
                dependency_note=dependency_note,
            ),
            steps=steps,
        )

    for turn_index in range(max_rounds * 2):
        round_number = (turn_index // 2) + 1
        rounds_completed = round_number
        current_agent = seller if turn_index % 2 == 0 else buyer
        current_floor = min_sell_price if current_agent.id == seller.id else manufacturer_floor_if_applicable(
            seller=current_agent,
            fallback=min_sell_price,
        )
        current_ceiling = max_buy_price

        tool_calls = [
            _review_state_event(
                agent_id=current_agent.id,
                step_index=step_index,
                phase=phase,
                negotiation_id=negotiation_id,
                round_number=round_number,
                delivered_message=delivered_message,
            ),
            _market_check_event(
                agent_id=current_agent.id,
                step_index=step_index,
                negotiation_id=negotiation_id,
                product_name=product_name,
                baseline_price=(seller_last_offer or buyer_last_offer or ((min_sell_price + max_buy_price) / 2)),
                role=current_agent.role,
                round_number=round_number,
            ),
        ]

        action = _decide_agent_action(
            openai_wrapper=openai_wrapper,
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
        )

        kind = action["action"]
        note = action.get("note", "").strip()
        reason = action.get("reason", "").strip()
        proposed_price = _coerce_price(action.get("price"))
        now = utc_now()

        if kind == "make_offer":
            if current_agent.id == seller.id:
                proposed_price = _bound_seller_offer(
                    proposed_price=proposed_price,
                    min_sell_price=min_sell_price,
                    max_buy_price=max_buy_price,
                    previous_offer=seller_last_offer,
                    counterparty_offer=buyer_last_offer,
                )
                seller_last_offer = proposed_price
            else:
                proposed_price = _bound_buyer_offer(
                    proposed_price=proposed_price,
                    min_sell_price=min_sell_price,
                    max_buy_price=max_buy_price,
                    previous_offer=buyer_last_offer,
                    counterparty_offer=seller_last_offer,
                )
                buyer_last_offer = proposed_price

            message = note or f"{current_agent.name} proposes {proposed_price:.2f} per unit."
            outcome = "Offer queued for delivery on the next turn."
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
                    created_at=now,
                    tool_calls=tool_calls,
                )
            )
            delivered_message = {
                "type": "offer",
                "price": proposed_price,
                "note": message,
                "from_agent_id": current_agent.id,
            }
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
                    message=note or f"{current_agent.name} accepts the pending offer.",
                    outcome="Negotiation ends with an accepted deal.",
                    proposed_price=final_price,
                    created_at=now,
                    tool_calls=tool_calls,
                )
            )
            status = NegotiationStatus.ACCEPTED
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
                    message=reason or f"{current_agent.name} rejects the pending offer.",
                    outcome="Negotiation ends with a rejection.",
                    proposed_price=delivered_message.get("price") if delivered_message else None,
                    created_at=now,
                    tool_calls=tool_calls,
                )
            )
            status = NegotiationStatus.REJECTED
            step_index += 1
            break
        else:
            fallback_price = (
                _bound_seller_offer(
                    proposed_price=None,
                    min_sell_price=min_sell_price,
                    max_buy_price=max_buy_price,
                    previous_offer=seller_last_offer,
                    counterparty_offer=buyer_last_offer,
                )
                if current_agent.id == seller.id
                else _bound_buyer_offer(
                    proposed_price=None,
                    min_sell_price=min_sell_price,
                    max_buy_price=max_buy_price,
                    previous_offer=buyer_last_offer,
                    counterparty_offer=seller_last_offer,
                )
            )
            if current_agent.id == seller.id:
                seller_last_offer = fallback_price
            else:
                buyer_last_offer = fallback_price

            message = note or f"{current_agent.name} submits {fallback_price:.2f} per unit."
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
                    created_at=now,
                    tool_calls=tool_calls,
                )
            )
            delivered_message = {
                "type": "offer",
                "price": fallback_price,
                "note": message,
                "from_agent_id": current_agent.id,
            }
            step_index += 1

    if status == NegotiationStatus.OPEN:
        status = NegotiationStatus.TIMEOUT
        steps.append(
            NegotiationStep(
                index=step_index,
                phase=phase,
                negotiation_id=negotiation_id,
                round_number=rounds_completed,
                agent_id=buyer.id,
                kind="timeout",
                message=f"{label} reached the round limit without agreement.",
                outcome="Negotiation times out.",
                proposed_price=None,
                created_at=utc_now(),
            )
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
            "Round limits can force timeouts even when the gap is narrowing.",
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
            "Tune reservation prices and round limits to test sensitivity.",
            "Add richer quantity or margin tradeoffs before introducing LLM behavior.",
        ],
    )


def _build_export_payload(run: RunRecord, trace_id: str | None) -> dict:
    return {
        "run_id": run.id,
        "title": run.title,
        "status": run.status,
        "trace_id": trace_id,
        "scenario": run.scenario,
        "negotiations": [negotiation.model_dump(mode="json") for negotiation in run.negotiations],
        "diagnosis": run.diagnosis.model_dump(mode="json"),
    }


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
        return f"{label} reached the round limit without agreement."
    return f"{label} remains open."


def _decide_agent_action(
    openai_wrapper: OpenAIClientWrapper,
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
    )
    try:
        decision = openai_wrapper.decide_action(prompt)
    except OpenAIDecisionError as exc:
        raise SimulationExecutionError(str(exc)) from exc

    if _is_valid_action(decision):
        return decision

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
        "max_rounds": max_rounds,
        "seller_id": seller.id,
        "buyer_id": buyer.id,
        "rules": [
            "Choose exactly one action.",
            "Actions: make_offer, accept_offer, reject_offer.",
            "Accept or reject only if you received an offer.",
            "Keep note short.",
            "Return JSON only.",
        ],
        "market_bounds": {
            "seller_floor": min_sell_price,
            "buyer_ceiling": max_buy_price,
        },
    }
    return (
        "You are a negotiation agent. Decide one action.\n"
        "Return JSON with keys action, price, note, reason.\n"
        "If action is make_offer, include price and short note.\n"
        "If action is accept_offer, price can be null.\n"
        "If action is reject_offer, include short reason.\n"
        f"{json.dumps(visible_state)}"
    )


def _bound_seller_offer(
    proposed_price: float | None,
    min_sell_price: float,
    max_buy_price: float,
    previous_offer: float | None,
    counterparty_offer: float | None,
) -> float:
    if proposed_price is None:
        anchor = previous_offer if previous_offer is not None else round(min_sell_price + (max_buy_price - min_sell_price) * 0.75, 2)
        if counterparty_offer is not None:
            anchor = max(min_sell_price, round(anchor - max((anchor - counterparty_offer) * 0.35, 1.0), 2))
        return round(max(min_sell_price, anchor), 2)

    bounded = max(min_sell_price, proposed_price)
    if previous_offer is not None:
        bounded = min(previous_offer, bounded)
    return round(bounded, 2)


def _bound_buyer_offer(
    proposed_price: float | None,
    min_sell_price: float,
    max_buy_price: float,
    previous_offer: float | None,
    counterparty_offer: float | None,
) -> float:
    if proposed_price is None:
        anchor = previous_offer if previous_offer is not None else round(max_buy_price - (max_buy_price - min_sell_price) * 0.75, 2)
        if counterparty_offer is not None:
            anchor = min(max_buy_price, round(anchor + max((counterparty_offer - anchor) * 0.45, 1.25), 2))
        return round(min(max_buy_price, anchor), 2)

    bounded = min(max_buy_price, proposed_price)
    if previous_offer is not None:
        bounded = max(previous_offer, bounded)
    return round(bounded, 2)


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
    agent_id: str,
    step_index: int,
    negotiation_id: str,
    product_name: str,
    baseline_price: float,
    role: AgentRole,
    round_number: int,
) -> ToolCallEvent:
    observed_price = _agent_market_price(
        baseline_price=baseline_price,
        role=role,
        round_number=round_number,
    )
    return ToolCallEvent(
        id=f"tool-{uuid4().hex[:8]}",
        step_index=step_index,
        agent_id=agent_id,
        tool_name="check_market_price",
        arguments={
            "negotiation_id": negotiation_id,
            "product": product_name,
        },
        result_summary=f"Observed market reference price: {observed_price:.2f}.",
        created_at=utc_now(),
    )


def _agent_market_price(
    baseline_price: float,
    role: AgentRole,
    round_number: int,
) -> float:
    role_bias = {
        AgentRole.SUPPLIER: 4.0,
        AgentRole.MANUFACTURER: 0.75,
        AgentRole.RETAILER: -2.5,
    }[role]
    round_bias = (round_number - 1) * 0.4
    return round(baseline_price + role_bias + round_bias, 2)


def _coerce_price(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _is_valid_action(decision: dict) -> bool:
    return decision.get("action") in {"make_offer", "accept_offer", "reject_offer"}


def manufacturer_floor_if_applicable(seller: Agent, fallback: float) -> float:
    return seller.reservation_prices.min_sell_price or fallback
