import Link from "next/link";
import { notFound } from "next/navigation";

import { ErrorState } from "../../../components/error-state";
import {
  ConversationMessage,
  NegotiationRecord,
  PhaseName,
  RunEvent,
  RunRecord,
} from "../../../lib/api-types";
import { getRunDetail } from "../../../lib/api";
import { formatDateTime, formatLabel } from "../../../lib/format";


type RunDetailPageProps = {
  params: Promise<{
    id: string;
  }>;
};

type ChartPoint = {
  label: string;
  value: number;
  meta: string;
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

export default async function RunDetailPage({ params }: RunDetailPageProps) {
  const { id } = await params;
  const result = await getRunDetail(id);

  if (!result.data && result.status === 404) {
    notFound();
  }

  if (!result.data) {
    return (
      <main className="panel">
        <div className="eyebrow">Run Detail</div>
        <h1>Run unavailable</h1>
        <ErrorState title="Unable to load run" message={result.error} />
        <div className="hero-actions">
          <Link className="button secondary" href="/runs">
            Back to Runs
          </Link>
        </div>
      </main>
    );
  }

  const detail = result.data;
  const run = detail.run;
  const conversation = detail.conversation ?? [];
  const eventLog = detail.event_log?.events ?? [];
  const beliefSamples = normalizeBeliefSamples(detail.derived?.belief_gap_samples);
  const averageBeliefGap =
    typeof detail.derived?.average_belief_gap === "number"
      ? detail.derived.average_belief_gap
      : null;
  const manufacturerMargin =
    typeof detail.derived?.manufacturer_margin_after_first_deal === "number"
      ? detail.derived.manufacturer_margin_after_first_deal
      : null;
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

  const supplierManufacturerChart = buildPriceChartPoints(
    run,
    "supplier_manufacturer",
  );
  const manufacturerRetailerChart = buildPriceChartPoints(
    run,
    "manufacturer_retailer",
  );
  const beliefComparison = buildBeliefComparison(beliefSamples);
  const totalMarginValue =
    typeof manufacturerMargin === "number"
      ? roundMoney(manufacturerMargin * run.product_context.target_quantity)
      : null;
  const transcriptMessages = [...conversation].sort((left, right) => left.index - right.index);
  const orderedEvents = [...eventLog].reverse();

  return (
    <main className="detail-layout">
      <section className="panel">
        <div className="eyebrow">Run Detail</div>
        <h1>{run.title}</h1>
        <p>{run.scenario}</p>

        <div className="summary-grid">
          <div className="summary-item">
            <span className="summary-label">Status</span>
            <span className="badge">{formatLabel(run.status)}</span>
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
          <Link className="button secondary" href="/runs">
            Back to Runs
          </Link>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <div className="eyebrow">1. Chats Between The Agents</div>
            <h2>Negotiations in parallel phone views</h2>
          </div>
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
                  {column.negotiation ? formatLabel(column.negotiation.status) : "Not Run"}
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
                      No transcript is available for this negotiation.
                    </div>
                  )}
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <div className="eyebrow">2. Supplier Vs Manufacturer Price Chart</div>
            <h2>Upstream price movement</h2>
          </div>
        </div>
        <PriceChart
          title="Supplier to Manufacturer"
          currency={run.product_context.currency}
          points={supplierManufacturerChart}
          benchmark={run.product_context.baseline_unit_price}
        />
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <div className="eyebrow">3. Manufacturer Vs Retailer Price Chart</div>
            <h2>Downstream price movement</h2>
          </div>
        </div>
        <PriceChart
          title="Manufacturer to Retailer"
          currency={run.product_context.currency}
          points={manufacturerRetailerChart}
          benchmark={run.product_context.baseline_unit_price}
        />
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
              <p>No market-check events were saved for this run.</p>
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

function buildPriceChartPoints(run: RunRecord, phase: PhaseName): ChartPoint[] {
  return run.steps
    .filter((step) => step.phase === phase && step.proposed_price !== null)
    .map((step) => ({
      label: `R${step.round_number}`,
      value: step.proposed_price ?? 0,
      meta: `${formatLabel(step.agent_id)} · ${formatLabel(step.kind)}`,
    }));
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
  title,
  currency,
  points,
  benchmark,
}: {
  title: string;
  currency: string;
  points: ChartPoint[];
  benchmark: number;
}) {
  const chartPoints = points.length > 0 ? points : [{ label: "n/a", value: benchmark, meta: "No offers" }];
  const values = [...chartPoints.map((point) => point.value), benchmark];
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const range = maxValue - minValue || 1;
  const width = 680;
  const height = 240;
  const padding = 28;
  const linePath = chartPoints
    .map((point, index) => {
      const x =
        chartPoints.length === 1
          ? width / 2
          : padding + (index * (width - padding * 2)) / (chartPoints.length - 1);
      const y =
        height -
        padding -
        ((point.value - minValue) / range) * (height - padding * 2);
      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");
  const benchmarkY =
    height -
    padding -
    ((benchmark - minValue) / range) * (height - padding * 2);

  return (
    <div className="chart-card">
      <div className="chart-summary">
        <div>
          <div className="eyebrow">{title}</div>
          <h3>{chartPoints.length} price points</h3>
        </div>
        <div className="run-meta">
          <span>Benchmark: {formatCurrency(benchmark, currency)}</span>
          <span>
            Range: {formatCurrency(minValue, currency)} to {formatCurrency(maxValue, currency)}
          </span>
        </div>
      </div>
      <div className="chart-shell">
        <svg
          aria-label={`${title} price chart`}
          className="price-chart"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
        >
          <line
            className="chart-benchmark"
            x1={padding}
            x2={width - padding}
            y1={benchmarkY}
            y2={benchmarkY}
          />
          <path className="chart-line" d={linePath} />
          {chartPoints.map((point, index) => {
            const x =
              chartPoints.length === 1
                ? width / 2
                : padding + (index * (width - padding * 2)) / (chartPoints.length - 1);
            const y =
              height -
              padding -
              ((point.value - minValue) / range) * (height - padding * 2);

            return (
              <g key={`${point.label}-${index}`}>
                <circle className="chart-dot" cx={x} cy={y} r="6" />
                <text className="chart-label" x={x} y={height - 8} textAnchor="middle">
                  {point.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="chart-point-grid">
        {points.length > 0 ? (
          points.map((point, index) => (
            <div className="detail-item" key={`${point.label}-${index}`}>
              <span className="summary-label">{point.label}</span>
              <strong>{formatCurrency(point.value, currency)}</strong>
              <span className="chart-point-meta">{point.meta}</span>
            </div>
          ))
        ) : (
          <div className="phase-empty">No offer prices were recorded for this phase.</div>
        )}
      </div>
    </div>
  );
}
