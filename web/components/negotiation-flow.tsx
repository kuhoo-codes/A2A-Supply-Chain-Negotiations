import { RunRecord } from "../lib/api-types";
import { formatDateTime, formatLabel } from "../lib/format";


type NegotiationFlowProps = {
  run: RunRecord;
};


export function NegotiationFlow({ run }: NegotiationFlowProps) {
  const agentMap = new Map(run.agents.map((agent) => [agent.id, agent]));

  return (
    <div className="phase-groups">
      {run.phases.map((phase) => {
        const negotiation = run.negotiations.find(
          (item) => item.phase === phase.name,
        );
        const steps = run.steps.filter((step) => step.phase === phase.name);

        return (
          <section className="phase-block" key={phase.name}>
            <div className="phase-header">
              <div>
                <div className="eyebrow">{phase.label}</div>
                <p>{phase.description}</p>
              </div>
              <span className="badge">
                {negotiation ? formatLabel(negotiation.status) : "Not Run"}
              </span>
            </div>

            {negotiation ? (
              <div className="phase-summary">
                <div className="run-meta">
                  <span>{negotiation.rounds_completed} rounds</span>
                  <span>{negotiation.quantity} units</span>
                  <span>
                    Final:{" "}
                    {negotiation.final_price !== null
                      ? `${negotiation.final_price} ${run.product_context.currency}`
                      : "No deal"}
                  </span>
                </div>
                <p>{negotiation.outcome_summary}</p>
              </div>
            ) : (
              <div className="phase-empty">
                This phase did not run because the upstream negotiation did not close.
              </div>
            )}

            {steps.length > 0 ? (
              <div className="step-stack">
                {steps.map((step) => {
                  const agent = agentMap.get(step.agent_id);
                  const marketCheck = step.tool_calls.find(
                    (toolCall) => toolCall.tool_name === "check_market_price",
                  );

                  return (
                    <article className="step-card" key={step.index}>
                      <div className="step-header">
                        <div>
                          <strong>{agent?.name ?? step.agent_id}</strong>
                          <span className="step-role">
                            {agent ? formatLabel(agent.role) : "Unknown"}
                          </span>
                        </div>
                        <span className="step-kind">
                          Round {step.round_number} · {formatLabel(step.kind)}
                        </span>
                      </div>
                      <div className="detail-grid">
                        <div className="detail-item">
                          <span className="summary-label">Action</span>
                          <span>{formatLabel(step.kind)}</span>
                        </div>
                        <div className="detail-item">
                          <span className="summary-label">Offer</span>
                          <span>
                            {step.proposed_price !== null
                              ? `${step.proposed_price} ${run.product_context.currency}`
                              : "n/a"}
                          </span>
                        </div>
                        <div className="detail-item">
                          <span className="summary-label">Market Check</span>
                          <span>{marketCheck?.result_summary ?? "n/a"}</span>
                        </div>
                      </div>
                      <p>{step.message}</p>
                      <div className="step-outcome">
                        <strong>Result</strong>
                        <span>{step.outcome}</span>
                      </div>
                      <div className="run-meta">
                        <span>{formatDateTime(step.created_at)}</span>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}
