"use client";

import { useEffect, useRef, useState } from "react";

import {
  NegotiationRecord,
  PhaseName,
  RunDetailResponse,
  RunEvent,
  RunRecord,
} from "../lib/api-types";
import { formatDateTime, formatLabel } from "../lib/format";


type LiveRunDetailProps = {
  initialDetail: RunDetailResponse;
};

type OfferTurnPoint = {
  turn: number;
  price: number;
  agentId: string;
};

type ReferenceLine = {
  label: string;
  value: number;
  tone: "market" | "seller" | "buyer" | "cost";
};

type ClosingMarker = {
  label: string;
  turn: number;
  price: number;
  status: string;
};

type NegotiationChartData = {
  title: string;
  sellerLabel: string;
  buyerLabel: string;
  sellerPoints: OfferTurnPoint[];
  buyerPoints: OfferTurnPoint[];
  references: ReferenceLine[];
  closingMarker: ClosingMarker | null;
};

type BeliefGapSample = {
  timestamp: string;
  phase: PhaseName | null;
  round: number | null;
  agent: string | null;
  observed_market_price: number;
  true_market_price: number;
  belief_gap: number;
};

const CHAT_PHASES: PhaseName[] = [
  "supplier_manufacturer",
  "manufacturer_retailer",
];

export function LiveRunDetail({ initialDetail }: LiveRunDetailProps) {
  const [detail, setDetail] = useState(initialDetail);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [highlightedMessageIndex, setHighlightedMessageIndex] = useState<number | null>(null);
  const previousMessageCount = useRef(initialDetail.conversation?.length ?? 0);

  useEffect(() => {
    setDetail(initialDetail);
    setRefreshError(null);
    setIsRefreshing(false);
    setHighlightedMessageIndex(null);
    previousMessageCount.current = initialDetail.conversation?.length ?? 0;
  }, [initialDetail]);

  useEffect(() => {
    if (detail.run.status !== "running") {
      return undefined;
    }

    const intervalId = window.setInterval(async () => {
      try {
        setIsRefreshing(true);
        const response = await fetch(`/api/runs/${detail.run.id}/detail`, {
          cache: "no-store",
        });
        const payload = (await response.json()) as {
          data: RunDetailResponse | null;
          error: string | null;
        };

        if (!response.ok || !payload.data) {
          setRefreshError(payload.error ?? "Unable to refresh live run detail.");
          setIsRefreshing(false);
          return;
        }

        const nextConversationCount = payload.data.conversation?.length ?? 0;
        if (nextConversationCount > previousMessageCount.current) {
          const latestMessage = payload.data.conversation?.[nextConversationCount - 1];
          setHighlightedMessageIndex(latestMessage?.index ?? null);
          window.setTimeout(() => setHighlightedMessageIndex(null), 2200);
        }
        previousMessageCount.current = nextConversationCount;
        setDetail(payload.data);
        setRefreshError(null);
      } catch {
        setRefreshError("Unable to refresh live run detail.");
      } finally {
        setIsRefreshing(false);
      }
    }, 1800);

    return () => window.clearInterval(intervalId);
  }, [detail.run.id, detail.run.status]);

  const run = detail.run;
  const conversation = detail.conversation ?? [];
  const eventLog = detail.event_log?.events ?? [];
  const beliefSamples =
    normalizeBeliefSamples(detail.derived?.belief_gap_samples).length > 0
      ? normalizeBeliefSamples(detail.derived?.belief_gap_samples)
      : buildBeliefSamplesFromEvents(eventLog, run.product_context.baseline_unit_price);
  const averageBeliefGap =
    typeof detail.derived?.average_belief_gap === "number"
      ? detail.derived.average_belief_gap
      : beliefSamples.length > 0
        ? roundMoney(
            beliefSamples.reduce((sum, sample) => sum + sample.belief_gap, 0) /
              beliefSamples.length,
          )
        : null;
  const manufacturerMargin =
    typeof detail.derived?.manufacturer_margin_after_first_deal === "number"
      ? detail.derived.manufacturer_margin_after_first_deal
      : deriveMarginFromNegotiations(run.negotiations);
  const suspectedFailureType =
    typeof detail.derived?.suspected_failure_type === "string"
      ? detail.derived.suspected_failure_type
      : null;
  const whereRunFailed = detail.derived?.where_run_failed as
    | { phase?: string; round?: number; agent?: string; note?: string }
    | undefined;

  const negotiationByPhase = new Map(
    run.negotiations.map((negotiation) => [negotiation.phase, negotiation]),
  );
  const chatColumns = CHAT_PHASES.map((phase) => {
    const negotiation = negotiationByPhase.get(phase);
    return {
      phase,
      negotiation,
      label: negotiation?.label ?? formatLabel(phase),
      messages: conversation.filter((message) => message.phase === phase),
    };
  });

  const supplierManufacturerChart = buildNegotiationChartData(run, "supplier_manufacturer");
  const manufacturerRetailerChart = buildNegotiationChartData(run, "manufacturer_retailer");
  const beliefComparison = buildBeliefComparison(beliefSamples);
  const totalMarginValue =
    typeof manufacturerMargin === "number"
      ? roundMoney(manufacturerMargin * run.product_context.target_quantity)
      : null;
  const transcriptMessages = [...conversation].sort((left, right) => left.index - right.index);
  const orderedEvents = [...eventLog].reverse();
  const liveStatusLabel = isRefreshing ? "Syncing" : "Live";

  return (
    <main className="detail-layout live-detail">
      <section className="detail-top-grid">
        <section className="panel chat-panel">
          <div className="section-heading">
            <div>
              <div className="eyebrow">1. Chats Between The Agents</div>
              <h2>Negotiations in parallel phone views</h2>
            </div>
            {run.status === "running" ? (
              <span className="text-link">Updates every 1.8s</span>
            ) : null}
          </div>
          <div className="phone-grid">
            {chatColumns.map((column) => (
              <article className="phone-card" key={column.phase}>
                <div className="phone-topbar">
                  <div>
                    <div className="eyebrow">{column.label}</div>
                    <strong>Messages</strong>
                  </div>
                  <span className={`badge ${column.negotiation?.status === "accepted" ? "leaf" : ""}`}>
                    {column.negotiation
                      ? formatLabel(column.negotiation.status)
                      : run.status === "running"
                        ? "Live"
                        : "Not Run"}
                  </span>
                </div>
                <div className="phone-frame">
                  <div className="phone-header">
                    <span>9:41</span>
                    <span>{column.label}</span>
                    <span>{column.messages.length} msgs</span>
                  </div>
                  <div className="phone-thread">
                    {column.messages.length > 0 ? (
                      column.messages.map((message) => (
                        <article
                          className={`iphone-bubble ${
                            isOutgoingMessage(column.phase, message.speaker_id)
                              ? "outgoing"
                              : "incoming"
                          } ${
                            highlightedMessageIndex === message.index ? "is-new" : ""
                          }`}
                          key={message.index}
                        >
                          <span className="bubble-speaker">{message.speaker_name}</span>
                          <p>{message.message}</p>
                          <div className="bubble-meta">
                            <span>Round {message.round}</span>
                            <span>{formatLabel(message.kind)}</span>
                            <span>
                              {message.offer_price !== null
                                ? formatCurrency(message.offer_price, message.currency)
                                : "No price"}
                            </span>
                          </div>
                        </article>
                      ))
                    ) : (
                      <div className="phase-empty">
                        {run.status === "running"
                          ? "Waiting for the first live message."
                          : "No transcript is available for this negotiation."}
                      </div>
                    )}
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>

        <div className="chart-stack">
          <section className="panel compact-panel">
            <div className="section-heading">
              <div>
                <div className="eyebrow">2. Supplier Vs Manufacturer Price Chart</div>
                <h2>Upstream price movement</h2>
              </div>
            </div>
            <PriceChart
              currency={run.product_context.currency}
              data={supplierManufacturerChart}
              compact
            />
          </section>

          <section className="panel compact-panel">
            <div className="section-heading">
              <div>
                <div className="eyebrow">3. Manufacturer Vs Retailer Price Chart</div>
                <h2>Downstream price movement</h2>
              </div>
            </div>
            <PriceChart
              currency={run.product_context.currency}
              data={manufacturerRetailerChart}
              compact
            />
          </section>
        </div>
      </section>

      <section className="detail-summary-panel">
        <div className="eyebrow">Run Detail</div>
        <h1>{run.title}</h1>
        <p>{run.scenario}</p>

        <div className="summary-grid">
          <div className="summary-item">
            <span className="summary-label">Status</span>
            <span className={`badge ${run.status === "running" ? "pulse" : ""}`}>
              {formatLabel(run.status)}
            </span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Created</span>
            <span>{formatDateTime(run.created_at)}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Product</span>
            <span>{run.product_context.product_name}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Market</span>
            <span>{run.product_context.market_region}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Quantity</span>
            <span>{run.product_context.target_quantity}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Baseline Price</span>
            <span>{formatCurrency(run.product_context.baseline_unit_price, run.product_context.currency)}</span>
          </div>
        </div>

        <div className="hero-actions">
          {run.status === "running" ? (
            <span className="badge leaf">{liveStatusLabel}</span>
          ) : null}
        </div>
        {refreshError ? <p className="inline-error">{refreshError}</p> : null}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <div className="eyebrow">4. Belief Comparison Panel</div>
            <h2>Observed market vs true market</h2>
          </div>
        </div>
        <div className="belief-grid">
          <div className="card">
            <div className="eyebrow">Market Anchor</div>
            <h3>{formatCurrency(run.product_context.baseline_unit_price, run.product_context.currency)}</h3>
            <p>True baseline unit price for the run.</p>
            <div className="run-meta">
              <span>
                Average gap:{" "}
                {typeof averageBeliefGap === "number"
                  ? formatSignedCurrency(averageBeliefGap, run.product_context.currency)
                  : "n/a"}
              </span>
              <span>{beliefSamples.length} samples</span>
            </div>
          </div>
          {beliefComparison.length > 0 ? (
            beliefComparison.map((item) => (
              <div className="card" key={item.agent}>
                <div className="eyebrow">{formatLabel(item.agent)}</div>
                <h3>{formatCurrency(item.observed, run.product_context.currency)}</h3>
                <p>{item.summary}</p>
                <div className="run-meta">
                  <span>
                    Gap: {formatSignedCurrency(item.gap, run.product_context.currency)}
                  </span>
                  <span>{item.phaseLabel}</span>
                  <span>{item.roundLabel}</span>
                </div>
              </div>
            ))
          ) : (
            <div className="card">
              <div className="eyebrow">Beliefs</div>
              <h3>No samples recorded</h3>
              <p>No market-check events have been persisted yet.</p>
            </div>
          )}
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <div className="eyebrow">5. Cascade / Margin Card</div>
            <h2>How the upstream deal propagated</h2>
          </div>
        </div>
        <div className="detail-columns two-up">
          <div className="card">
            <div className="eyebrow">Price Cascade</div>
            <h3>{run.diagnosis.chain_effect}</h3>
            <div className="detail-grid cascade-grid">
              <div className="detail-item">
                <span className="summary-label">Supplier → Manufacturer</span>
                <span>
                  {formatNegotiationPrice(
                    negotiationByPhase.get("supplier_manufacturer"),
                    run.product_context.currency,
                  )}
                </span>
              </div>
              <div className="detail-item">
                <span className="summary-label">Manufacturer → Retailer</span>
                <span>
                  {formatNegotiationPrice(
                    negotiationByPhase.get("manufacturer_retailer"),
                    run.product_context.currency,
                  )}
                </span>
              </div>
              <div className="detail-item">
                <span className="summary-label">Quantity</span>
                <span>{run.product_context.target_quantity}</span>
              </div>
            </div>
          </div>
          <div className="card">
            <div className="eyebrow">Margin Snapshot</div>
            <h3>
              {typeof manufacturerMargin === "number"
                ? formatCurrency(manufacturerMargin, run.product_context.currency)
                : "n/a"}
            </h3>
            <p>
              Manufacturer margin after the upstream deal and before downstream
              quantity expansion.
            </p>
            <div className="run-meta">
              <span>
                Total spread:{" "}
                {totalMarginValue !== null
                  ? formatCurrency(totalMarginValue, run.product_context.currency)
                  : "n/a"}
              </span>
              <span>
                Outcome: {formatLabel(negotiationByPhase.get("manufacturer_retailer")?.status ?? "open")}
              </span>
            </div>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <div className="eyebrow">6. Diagnosis Card</div>
            <h2>Run interpretation</h2>
          </div>
        </div>
        <div className="detail-columns two-up">
          <div className="card">
            <div className="eyebrow">Outcome</div>
            <h3>{run.diagnosis.outcome}</h3>
            <p>{whereRunFailed?.note ?? "No explicit failure point was inferred for this run."}</p>
            <div className="run-meta">
              <span>
                Failure type:{" "}
                {suspectedFailureType ? formatLabel(suspectedFailureType) : "None"}
              </span>
              <span>
                Phase: {whereRunFailed?.phase ? formatLabel(whereRunFailed.phase) : "n/a"}
              </span>
              <span>Round: {whereRunFailed?.round ?? "n/a"}</span>
            </div>
          </div>
          <div className="card">
            <div className="eyebrow">Signals</div>
            <h3>Risks and next actions</h3>
            <div className="diagnosis-columns">
              <div>
                <strong>Key risks</strong>
                <ul className="plain-list">
                  {run.diagnosis.key_risks.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
              <div>
                <strong>Key signals</strong>
                <ul className="plain-list">
                  {run.diagnosis.key_signals.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
              <div>
                <strong>Next actions</strong>
                <ul className="plain-list">
                  {run.diagnosis.suggested_next_actions.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <div className="eyebrow">7. Transcript And Event Log Below</div>
            <h2>Full execution record</h2>
          </div>
        </div>
        <div className="detail-columns two-up">
          <div>
            <div className="eyebrow">Transcript</div>
            {transcriptMessages.length > 0 ? (
              <div className="conversation-stack">
                {transcriptMessages.map((message) => (
                  <article className="conversation-card" key={message.index}>
                    <div className="step-header">
                      <div>
                        <strong>{message.speaker_name}</strong>
                        <span className="step-role">
                          {message.speaker_role
                            ? formatLabel(message.speaker_role)
                            : "System"}
                        </span>
                      </div>
                      <span className="step-kind">
                        {formatLabel(message.phase)} · Round {message.round}
                      </span>
                    </div>
                    <p>{message.message}</p>
                    <div className="run-meta">
                      <span>{formatDateTime(message.timestamp)}</span>
                      <span>{formatLabel(message.kind)}</span>
                      <span>
                        {message.offer_price !== null
                          ? formatCurrency(message.offer_price, message.currency)
                          : "No price"}
                      </span>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="phase-empty">No saved transcript is available for this run.</div>
            )}
          </div>
          <div>
            <div className="eyebrow">Event Log</div>
            {orderedEvents.length > 0 ? (
              <div className="event-stack">
                {orderedEvents.map((event, index) => (
                  <article className="event-card" key={`${event.timestamp}-${index}`}>
                    <div className="step-header">
                      <div>
                        <strong>{formatLabel(event.event_type)}</strong>
                        <span className="step-role">
                          {event.agent ? formatLabel(event.agent) : "System"}
                        </span>
                      </div>
                      <span className="step-kind">
                        {event.phase ? formatLabel(event.phase) : "Run"}
                        {event.round ? ` · Round ${event.round}` : ""}
                      </span>
                    </div>
                    <div className="run-meta">
                      <span>{formatDateTime(event.timestamp)}</span>
                      <span>
                        Offer:{" "}
                        {event.offer_price !== null
                          ? formatCurrency(event.offer_price, run.product_context.currency)
                          : "n/a"}
                      </span>
                      <span>
                        Market:{" "}
                        {event.observed_market_price !== null
                          ? formatCurrency(
                              event.observed_market_price,
                              run.product_context.currency,
                            )
                          : "n/a"}
                      </span>
                    </div>
                    <p>{event.note ?? "No additional note recorded."}</p>
                  </article>
                ))}
              </div>
            ) : (
              <div className="phase-empty">No event log is available for this run.</div>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}

function buildNegotiationChartData(
  run: RunRecord,
  phase: PhaseName,
): NegotiationChartData {
  const negotiation = run.negotiations.find((item) => item.phase === phase);
  const phaseSteps = run.steps
    .filter((step) => step.phase === phase)
    .sort((left, right) => left.index - right.index);
  const offerSteps = phaseSteps.filter(
    (step) => step.kind === "offer" && step.proposed_price !== null,
  );
  const sellerAgentId = negotiation?.seller_agent_id ?? (phase === "supplier_manufacturer" ? "supplier" : "manufacturer");
  const buyerAgentId = negotiation?.buyer_agent_id ?? (phase === "supplier_manufacturer" ? "manufacturer" : "retailer");

  const indexedOffers = offerSteps.map((step, index) => ({
    turn: index + 1,
    price: step.proposed_price ?? 0,
    agentId: step.agent_id,
  }));

  const sellerPoints = indexedOffers.filter((point) => point.agentId === sellerAgentId);
  const buyerPoints = indexedOffers.filter((point) => point.agentId === buyerAgentId);
  const supplier = run.agents.find((agent) => agent.id === "supplier");
  const manufacturer = run.agents.find((agent) => agent.id === "manufacturer");
  const retailer = run.agents.find((agent) => agent.id === "retailer");
  const upstreamNegotiation = run.negotiations.find(
    (item) => item.phase === "supplier_manufacturer",
  );

  const references: ReferenceLine[] = [
    {
      label: "True market price",
      value: run.product_context.baseline_unit_price,
      tone: "market",
    },
  ];

  if (phase === "supplier_manufacturer") {
    if (supplier?.reservation_prices.min_sell_price !== null && supplier?.reservation_prices.min_sell_price !== undefined) {
      references.push({
        label: "Supplier reservation price",
        value: supplier.reservation_prices.min_sell_price,
        tone: "seller",
      });
    }
    if (manufacturer?.reservation_prices.max_buy_price !== null && manufacturer?.reservation_prices.max_buy_price !== undefined) {
      references.push({
        label: "Manufacturer reservation price",
        value: manufacturer.reservation_prices.max_buy_price,
        tone: "buyer",
      });
    }
  } else {
    if (manufacturer?.reservation_prices.min_sell_price !== null && manufacturer?.reservation_prices.min_sell_price !== undefined) {
      references.push({
        label: "Manufacturer reservation price",
        value: manufacturer.reservation_prices.min_sell_price,
        tone: "seller",
      });
    }
    if (retailer?.reservation_prices.max_buy_price !== null && retailer?.reservation_prices.max_buy_price !== undefined) {
      references.push({
        label: "Retailer reservation price",
        value: retailer.reservation_prices.max_buy_price,
        tone: "buyer",
      });
    }
    if (upstreamNegotiation?.final_price !== null && upstreamNegotiation?.final_price !== undefined) {
      references.push({
        label: "Manufacturer upstream cost",
        value: upstreamNegotiation.final_price,
        tone: "cost",
      });
    }
  }

  const lastOffer = indexedOffers[indexedOffers.length - 1] ?? null;
  let closingMarker: ClosingMarker | null = null;
  if (negotiation?.status === "accepted" && negotiation.final_price !== null) {
    closingMarker = {
      label: "Accepted price",
      turn: lastOffer?.turn ?? 1,
      price: negotiation.final_price,
      status: negotiation.status,
    };
  } else if (lastOffer) {
    closingMarker = {
      label: "Last offer",
      turn: lastOffer.turn,
      price: lastOffer.price,
      status: negotiation?.status ?? "open",
    };
  }

  return {
    title:
      phase === "supplier_manufacturer"
        ? "supplier vs manufacturer"
        : "manufacturer vs retailer",
    sellerLabel: formatLabel(sellerAgentId),
    buyerLabel: formatLabel(buyerAgentId),
    sellerPoints,
    buyerPoints,
    references,
    closingMarker,
  };
}

function normalizeBeliefSamples(value: unknown): BeliefGapSample[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.flatMap((item) => {
    const sample = item as {
      timestamp?: unknown;
      phase?: unknown;
      round?: unknown;
      agent?: unknown;
      observed_market_price?: unknown;
      true_market_price?: unknown;
      belief_gap?: unknown;
    };

    if (
      !item ||
      typeof item !== "object" ||
      typeof sample.observed_market_price !== "number" ||
      typeof sample.true_market_price !== "number" ||
      typeof sample.belief_gap !== "number"
    ) {
      return [];
    }

    return [
      {
        timestamp: typeof sample.timestamp === "string" ? sample.timestamp : "",
        phase:
          sample.phase === "supplier_manufacturer" || sample.phase === "manufacturer_retailer"
            ? sample.phase
            : null,
        round: typeof sample.round === "number" ? sample.round : null,
        agent: typeof sample.agent === "string" ? sample.agent : null,
        observed_market_price: sample.observed_market_price,
        true_market_price: sample.true_market_price,
        belief_gap: sample.belief_gap,
      },
    ];
  });
}

function buildBeliefSamplesFromEvents(events: RunEvent[], trueMarketPrice: number): BeliefGapSample[] {
  return events
    .filter(
      (event) =>
        event.event_type === "market_price_check" &&
        event.observed_market_price !== null,
    )
    .map((event) => ({
      timestamp: event.timestamp,
      phase: event.phase,
      round: event.round,
      agent: event.agent,
      observed_market_price: event.observed_market_price ?? trueMarketPrice,
      true_market_price: trueMarketPrice,
      belief_gap: roundMoney((event.observed_market_price ?? trueMarketPrice) - trueMarketPrice),
    }));
}

function buildBeliefComparison(samples: BeliefGapSample[]) {
  const latestByAgent = new Map<string, BeliefGapSample>();

  for (const sample of samples) {
    if (!sample.agent) {
      continue;
    }

    latestByAgent.set(sample.agent, sample);
  }

  return Array.from(latestByAgent.entries()).map(([agent, sample]) => ({
    agent,
    observed: sample.observed_market_price,
    gap: sample.belief_gap,
    phaseLabel: sample.phase ? formatLabel(sample.phase) : "Unknown phase",
    roundLabel: sample.round ? `Round ${sample.round}` : "No round",
    summary:
      sample.belief_gap > 0
        ? "This agent priced the market above the baseline."
        : sample.belief_gap < 0
          ? "This agent priced the market below the baseline."
          : "This agent matched the baseline exactly.",
  }));
}

function deriveMarginFromNegotiations(negotiations: NegotiationRecord[]): number | null {
  const first = negotiations.find((item) => item.phase === "supplier_manufacturer");
  const second = negotiations.find((item) => item.phase === "manufacturer_retailer");

  if (!first?.final_price || !second?.final_price) {
    return null;
  }

  return roundMoney(second.final_price - first.final_price);
}

function isOutgoingMessage(phase: PhaseName, speakerId: string): boolean {
  if (phase === "supplier_manufacturer") {
    return speakerId === "manufacturer";
  }

  return speakerId === "retailer";
}

function formatCurrency(value: number, currency: string): string {
  return `${roundMoney(value).toFixed(2)} ${currency}`;
}

function formatSignedCurrency(value: number, currency: string): string {
  const rounded = roundMoney(value).toFixed(2);
  return `${value > 0 ? "+" : ""}${rounded} ${currency}`;
}

function roundMoney(value: number): number {
  return Math.round(value * 100) / 100;
}

function formatNegotiationPrice(
  negotiation: NegotiationRecord | undefined,
  currency: string,
): string {
  if (!negotiation || negotiation.final_price === null) {
    return "No final price";
  }

  return formatCurrency(negotiation.final_price, currency);
}

function PriceChart({
  currency,
  data,
  compact = false,
}: {
  currency: string;
  data: NegotiationChartData;
  compact?: boolean;
}) {
  const chartPoints = [...data.sellerPoints, ...data.buyerPoints];
  const fallbackReference = data.references[0]?.value ?? 0;
  const values = [
    ...chartPoints.map((point) => point.price),
    ...data.references.map((reference) => reference.value),
    ...(data.closingMarker ? [data.closingMarker.price] : []),
    fallbackReference,
  ];
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const range = maxValue - minValue || 1;
  const width = 680;
  const height = compact ? 170 : 240;
  const padding = compact ? 22 : 28;
  const maxTurn = Math.max(
    ...chartPoints.map((point) => point.turn),
    data.closingMarker?.turn ?? 1,
    1,
  );

  function getX(turn: number): number {
    return maxTurn === 1
      ? width / 2
      : padding + ((turn - 1) * (width - padding * 2)) / (maxTurn - 1);
  }

  function getY(price: number): number {
    return (
      height -
      padding -
      ((price - minValue) / range) * (height - padding * 2)
    );
  }

  function buildPath(points: OfferTurnPoint[]): string {
    return points
      .map((point, index) => `${index === 0 ? "M" : "L"} ${getX(point.turn)} ${getY(point.price)}`)
      .join(" ");
  }

  return (
    <div className={`chart-card ${compact ? "compact" : ""}`}>
      <div className="chart-summary">
        <div>
          <div className="eyebrow">{data.title}</div>
          <h3>{chartPoints.length} offer points</h3>
        </div>
        <div className="run-meta">
          <span>X-axis: Turn number</span>
          <span>Y-axis: Price</span>
          <span>
            Range: {formatCurrency(minValue, currency)} to {formatCurrency(maxValue, currency)}
          </span>
        </div>
      </div>
      <div className="chart-shell">
        <svg
          aria-label={`${data.title} price chart`}
          className="price-chart"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
        >
          {data.references.map((reference) => (
            <line
              key={reference.label}
              className={`chart-reference ${reference.tone}`}
              x1={padding}
              x2={width - padding}
              y1={getY(reference.value)}
              y2={getY(reference.value)}
            />
          ))}
          {data.sellerPoints.length > 0 ? (
            <path className="chart-line seller" d={buildPath(data.sellerPoints)} />
          ) : null}
          {data.buyerPoints.length > 0 ? (
            <path className="chart-line buyer" d={buildPath(data.buyerPoints)} />
          ) : null}
          {data.sellerPoints.map((point) => (
            <circle
              className="chart-dot seller"
              cx={getX(point.turn)}
              cy={getY(point.price)}
              key={`seller-${point.turn}-${point.price}`}
              r="4.5"
            />
          ))}
          {data.buyerPoints.map((point) => (
            <circle
              className="chart-dot buyer"
              cx={getX(point.turn)}
              cy={getY(point.price)}
              key={`buyer-${point.turn}-${point.price}`}
              r="4.5"
            />
          ))}
          {Array.from({ length: maxTurn }, (_, index) => index + 1).map((turn) => (
            <text
              className="chart-label"
              key={`turn-${turn}`}
              x={getX(turn)}
              y={height - 8}
              textAnchor="middle"
            >
              {turn}
            </text>
          ))}
          {data.closingMarker ? (
            <g>
              <circle
                className="chart-marker"
                cx={getX(data.closingMarker.turn)}
                cy={getY(data.closingMarker.price)}
                r="7"
              />
              <text
                className="chart-marker-label"
                x={getX(data.closingMarker.turn)}
                y={getY(data.closingMarker.price) - 10}
                textAnchor="middle"
              >
                {data.closingMarker.label}
              </text>
            </g>
          ) : null}
        </svg>
      </div>
      <div className="chart-legend">
        <div className="chart-legend-group">
          <span className="chart-chip seller">{data.sellerLabel} offers</span>
          <span className="chart-chip buyer">{data.buyerLabel} offers</span>
        </div>
        <div className="chart-reference-list">
          {data.references.map((reference) => (
            <span className={`chart-chip ${reference.tone}`} key={reference.label}>
              {reference.label}: {formatCurrency(reference.value, currency)}
            </span>
          ))}
          {data.closingMarker ? (
            <span className="chart-chip marker">
              {data.closingMarker.label}: {formatCurrency(data.closingMarker.price, currency)}
            </span>
          ) : null}
        </div>
      </div>
      {chartPoints.length === 0 ? (
        <div className="phase-empty">No offer prices were recorded for this phase.</div>
      ) : null}
    </div>
  );
}
