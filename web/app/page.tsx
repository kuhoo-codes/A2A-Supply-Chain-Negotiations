import { InfoPanel } from "../components/info-panel";
import { RunSeedForm } from "../components/run-seed-form";
export default async function HomePage() {
  return (
    <main>
      <section className="panel">
        <div className="runs-page-header">
          <div className="runs-page-copy">
            <div className="eyebrow">Runs</div>
            <h1>Runs</h1>
            <p>
              Each run is one saved seller, manufacturer, and retailer negotiation chain.
              Running a seed creates three new runs at once.
            </p>
          </div>

          <div className="page-actions">
            <RunSeedForm mode="redirect" />
          </div>
        </div>
      </section>

    </main>
  );
}
