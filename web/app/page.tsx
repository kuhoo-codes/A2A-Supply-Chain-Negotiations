import Link from "next/link";

import { ErrorState } from "../components/error-state";
import { HealthStatus } from "../components/health-status";
import { InfoPanel } from "../components/info-panel";
import { RunSimulationForm } from "../components/run-simulation-form";
import { RunCard } from "../components/run-card";
import { getApiBaseUrl, getBackendHealth, getRuns } from "../lib/api";


export default async function HomePage() {
  const [healthResult, runsResult] = await Promise.all([
    getBackendHealth(),
    getRuns(),
  ]);
  const latestRuns = runsResult.data?.slice(0, 3) ?? [];

  return (
    <main>
      <section className="hero">
        <div className="eyebrow">Negotiation Workspace</div>
        <h1>A2A Supply Chain Negotiations</h1>
        <p>Minimal interface for reviewing deterministic negotiation runs.</p>
        <HealthStatus
          error={healthResult.error}
          status={healthResult.data?.status ?? null}
        />
        <div className="hero-actions">
          <Link className="button secondary" href="/runs">
            View Runs
          </Link>
          <a className="button secondary" href={`${getApiBaseUrl()}/docs`}>
            API Docs
          </a>
        </div>
        <div className="hero-tools">
          <RunSimulationForm mode="redirect" />
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <div className="eyebrow">Latest Runs</div>
            <h2>Recent records</h2>
          </div>
          <Link className="text-link" href="/runs">
            See all runs
          </Link>
        </div>

        {runsResult.error ? (
          <ErrorState title="Runs unavailable" message={runsResult.error} />
        ) : latestRuns.length > 0 ? (
          <div className="runs-grid">
            {latestRuns.map((run) => (
              <RunCard key={run.id} run={run} />
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <h2>No runs yet</h2>
            <p>Saved run records will appear here once they are available.</p>
          </div>
        )}
      </section>

      <section className="section-grid compact">
        <InfoPanel
          title="Simulation"
          description="Reserved for scenario setup, agent configuration, and manual simulation controls."
        />
        <InfoPanel
          title="Traces"
          description="Reserved for Langfuse trace links and execution-level inspection."
        />
        <InfoPanel
          title="Diagnosis"
          description="Reserved for concise run assessment, negotiation friction, and next-action summaries."
        />
      </section>
    </main>
  );
}
