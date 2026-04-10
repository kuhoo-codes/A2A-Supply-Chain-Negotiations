import Link from "next/link";
import { notFound } from "next/navigation";

import { ErrorState } from "../../../components/error-state";
import { NegotiationFlow } from "../../../components/negotiation-flow";
import { getRun } from "../../../lib/api";
import { formatDateTime, formatLabel } from "../../../lib/format";


type RunDetailPageProps = {
  params: Promise<{
    id: string;
  }>;
};


export default async function RunDetailPage({ params }: RunDetailPageProps) {
  const { id } = await params;
  const result = await getRun(id);

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

  const run = result.data;

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
            <span className="summary-label">Updated</span>
            <span>{formatDateTime(run.updated_at)}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Agents</span>
            <span>{run.agents.length}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Steps</span>
            <span>{run.steps.length}</span>
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
            <span className="summary-label">Max Rounds</span>
            <span>{run.max_rounds_per_negotiation}</span>
          </div>
        </div>

        <div className="hero-actions">
          <Link className="button secondary" href="/runs">
            Back to Runs
          </Link>
        </div>
      </section>

      <section className="panel">
        <div className="eyebrow">Final Status</div>
        <h2>Phase outcomes</h2>
        <div className="detail-columns two-up">
          {run.negotiations.map((negotiation) => (
            <div className="card" key={negotiation.id}>
              <div className="eyebrow">{negotiation.label}</div>
              <h3>{formatLabel(negotiation.status)}</h3>
              <div className="run-meta">
                <span>{negotiation.rounds_completed} rounds</span>
                <span>{negotiation.quantity} units</span>
                <span>
                  {negotiation.final_price
                    ? `${negotiation.final_price} ${run.product_context.currency}`
                    : "No final price"}
                </span>
              </div>
              <p>{negotiation.outcome_summary}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="eyebrow">Run Summary</div>
        <h2>Agents and constraints</h2>
        <div className="detail-columns">
          {run.agents.map((agent) => (
            <div className="card" key={agent.id}>
              <div className="eyebrow">{formatLabel(agent.role)}</div>
              <h3>{agent.name}</h3>
              <p>{agent.objective}</p>
              <div className="run-meta">
                <span>
                  Min sell:{" "}
                  {agent.reservation_prices.min_sell_price ?? "n/a"}
                </span>
                <span>
                  Max buy:{" "}
                  {agent.reservation_prices.max_buy_price ?? "n/a"}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <div className="eyebrow">Negotiation Flow</div>
            <h2>Phase by phase</h2>
          </div>
        </div>
        <NegotiationFlow run={run} />
      </section>
    </main>
  );
}
