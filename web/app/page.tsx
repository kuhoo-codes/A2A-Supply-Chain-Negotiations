import Link from "next/link";

import { InfoPanel } from "../components/info-panel";
import { RunSeedForm } from "../components/run-seed-form";
import { getApiBaseUrl } from "../lib/api";


export default async function HomePage() {
  return (
    <main>
      <section className="hero">
        <div className="eyebrow">Tomato Ketchup Ops</div>
        <h1>Run three seller, manufacturer, and retailer negotiations from one seed.</h1>
        <p>
          Enter one random seed and the system generates three tomato-ketchup
          supply chain simulations across seller, manufacturer, and retailer deal flows.
        </p>
        <div className="hero-actions">
          <Link className="button secondary" href="/runs">
            View Runs
          </Link>
          <a className="button secondary" href={`${getApiBaseUrl()}/docs`}>
            API Docs
          </a>
        </div>
        <div className="hero-tools">
          <RunSeedForm mode="redirect" />
        </div>
      </section>

      <section className="section-grid compact">
        <InfoPanel
          title="Simulation"
          description="Each seed creates three ketchup supply chain simulations with saved seller, manufacturer, and retailer negotiations."
        />
        <InfoPanel
          title="Traces"
          description="Later this will hold trace links and step-level execution metadata for each generated run."
        />
        <InfoPanel
          title="Website"
          description="The interface now assumes a tomato-ketchup business context instead of a generic negotiation workspace."
        />
      </section>
    </main>
  );
}
