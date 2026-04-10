import { EmptyState } from "../../components/empty-state";
import { ErrorState } from "../../components/error-state";
import { RunSeedForm } from "../../components/run-seed-form";
import { RunCard } from "../../components/run-card";
import { getRuns } from "../../lib/api";


export default async function RunsPage() {
  const result = await getRuns();

  return (
    <main className="panel">
      <div className="eyebrow">Runs</div>
      <h1>Runs</h1>
      <p>
        Each run is one saved seller, manufacturer, and retailer negotiation chain.
        Running a seed creates three new runs at once.
      </p>

      <div className="page-actions">
        <RunSeedForm />
      </div>

      {result.error ? (
        <ErrorState title="Unable to load runs" message={result.error} />
      ) : result.data && result.data.length > 0 ? (
        <section className="runs-grid">
          {result.data.map((run) => (
            <RunCard key={run.id} run={run} />
          ))}
        </section>
      ) : (
        <EmptyState
          title="No runs found"
          message="Run a simulation and the new record will appear here."
        />
      )}
    </main>
  );
}
