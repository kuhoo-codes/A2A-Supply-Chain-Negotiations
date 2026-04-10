"use client";

import { useState } from "react";

import { SimulationTestPipelineResult } from "../lib/api-types";
import { formatDateTime } from "../lib/format";


type PipelineState =
  | {
      loading: false;
      error: null;
      result: null;
    }
  | {
      loading: true;
      error: null;
      result: null;
    }
  | {
      loading: false;
      error: string;
      result: null;
    }
  | {
      loading: false;
      error: null;
      result: SimulationTestPipelineResult;
    };


export function PipelineTestButton() {
  const [state, setState] = useState<PipelineState>({
    loading: false,
    error: null,
    result: null,
  });

  async function handleClick() {
    setState({ loading: true, error: null, result: null });

    try {
      const response = await fetch("/api/simulation/test-pipeline", {
        method: "POST",
      });

      const payload = (await response.json()) as
        | { data: SimulationTestPipelineResult | null; error: string | null };

      if (!response.ok || !payload.data) {
        setState({
          loading: false,
          error: payload.error ?? "Pipeline test failed.",
          result: null,
        });
        return;
      }

      setState({
        loading: false,
        error: null,
        result: payload.data,
      });
    } catch {
      setState({
        loading: false,
        error: "Unable to reach the frontend API route.",
        result: null,
      });
    }
  }

  return (
    <div className="pipeline-test">
      <button
        className="button secondary"
        disabled={state.loading}
        onClick={handleClick}
        type="button"
      >
        {state.loading ? "Testing Pipeline..." : "Test Pipeline"}
      </button>

      {state.error ? (
        <div className="error-state compact" role="alert">
          <h2>Pipeline test failed</h2>
          <p>{state.error}</p>
        </div>
      ) : null}

      {state.result ? (
        <section className="pipeline-result">
          <div className="status-row">
            <div>
              <div className="eyebrow">Pipeline Result</div>
              <p className="muted-copy">{state.result.message}</p>
            </div>
            <span className={state.result.success ? "badge" : "badge danger"}>
              {state.result.success ? "Success" : "Partial"}
            </span>
          </div>

          <div className="summary-grid compact-grid">
            <div className="summary-item">
              <span className="summary-label">Run</span>
              <span>{state.result.run_id}</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Trace</span>
              <span>{state.result.trace_id ?? "Not created"}</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Export</span>
              <span>
                {state.result.export
                  ? formatDateTime(state.result.export.created_at)
                  : "Not created"}
              </span>
            </div>
          </div>

          <div className="detail-columns two-up">
            <div className="card">
              <div className="eyebrow">OpenAI</div>
              <p>{state.result.openai.message}</p>
              <div className="run-meta">
                <span>{state.result.openai.configured ? "Configured" : "Missing key"}</span>
                <span>{state.result.openai.available ? "Available" : "Unavailable"}</span>
              </div>
            </div>
            <div className="card">
              <div className="eyebrow">Langfuse</div>
              <p>{state.result.langfuse.message}</p>
              <div className="run-meta">
                <span>
                  {state.result.langfuse.configured ? "Configured" : "Missing key"}
                </span>
                <span>{state.result.langfuse.available ? "Available" : "Unavailable"}</span>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="eyebrow">Events</div>
            <ul className="plain-list">
              {state.result.events.map((event) => (
                <li key={event}>{event}</li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}
    </div>
  );
}
