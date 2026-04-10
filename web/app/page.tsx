import Link from "next/link";

import { RunSeedForm } from "../components/run-seed-form";


const SIGNALS = [
  {
    eyebrow: "Market Signal",
    title: "Harvest pressure meets retail demand",
    body:
      "Supplier, manufacturer, and retailer agents negotiate sequentially while reacting to noisy market references and operator shocks.",
  },
  {
    eyebrow: "Diagnosis Layer",
    title: "See why a run failed, not just that it failed",
    body:
      "Every turn captures offers, market checks, private reasoning traces, and chain effects so you can inspect where the negotiation broke.",
  },
  {
    eyebrow: "Operator Control",
    title: "Inject disruptions mid-run",
    body:
      "Queue price spikes, shortages, demand surges, or geopolitical events and watch how stale assumptions ripple through the supply chain.",
  },
];

const SCENES = [
  "Supplier anchors raw tomato paste pricing against patchy harvest yields.",
  "Manufacturer protects margin while translating upstream cost into finished ketchup economics.",
  "Retailer pushes for shelf-ready volume without overpaying during demand swings.",
];

export default async function HomePage() {
  return (
    <main className="home-page">
      <section className="hero tomato-hero">
        <div className="tomato-hero-copy">
          <div className="eyebrow">Tomato Ketchup Market Simulation</div>
          <h1>Trace how pricing pressure moves from farm-side supply into the ketchup aisle.</h1>
          <p>
            This workspace simulates sequential AI negotiations across the tomato ketchup
            supply chain. Run new scenarios, inject market shocks, and inspect why a deal
            cleared, stalled, or collapsed.
          </p>

          <div className="hero-actions">
            <Link className="button secondary" href="/runs">
              Explore Saved Runs
            </Link>
          </div>

          <div className="tomato-hero-stats">
            <div className="tomato-stat">
              <span className="tomato-stat-value">3</span>
              <span className="tomato-stat-label">agents in chain</span>
            </div>
            <div className="tomato-stat">
              <span className="tomato-stat-value">2</span>
              <span className="tomato-stat-label">bilateral deals</span>
            </div>
            <div className="tomato-stat">
              <span className="tomato-stat-value">1</span>
              <span className="tomato-stat-label">cascading outcome</span>
            </div>
          </div>
        </div>

        <aside className="tomato-launch-card">
          <div className="eyebrow">Launch Simulation Batch</div>
          <h2>Spin up fresh ketchup-market runs</h2>
          <p>
            Use a seed to generate three new supply-chain negotiations with varied market
            conditions and traces.
          </p>
          <RunSeedForm mode="redirect" />
          <div className="tomato-launch-note">
            Runs open in the analysis workspace with chat replay, price movement, belief
            divergence, and downloadable logs.
          </div>
        </aside>
      </section>

      <section className="panel tomato-signal-panel">
        <div className="section-heading">
          <div>
            <div className="eyebrow">What This Shows</div>
            <h2>Negotiation behavior under uncertain tomato-market conditions</h2>
          </div>
        </div>
        <div className="section-grid">
          {SIGNALS.map((item) => (
            <article className="card tomato-info-card" key={item.title}>
              <div className="eyebrow">{item.eyebrow}</div>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="tomato-story-grid">
        <article className="panel tomato-story-panel">
          <div className="eyebrow">Chain Narrative</div>
          <h2>One upstream concession can distort the entire run</h2>
          <p>
            Supplier-to-manufacturer pricing sets the manufacturer cost basis, which then
            constrains what the manufacturer can credibly offer the retailer. The point is
            not to make the agents perfect negotiators. The point is to make their traces
            legible when they are wrong.
          </p>
          <div className="tomato-scene-list">
            {SCENES.map((scene) => (
              <div className="tomato-scene" key={scene}>
                {scene}
              </div>
            ))}
          </div>
        </article>

        <article className="panel tomato-operator-panel">
          <div className="eyebrow">Operator View</div>
          <h2>Designed for diagnosis, not just replay</h2>
          <div className="tomato-operator-stack">
            <div className="tomato-operator-item">
              <strong>What happened</strong>
              <p>Replay negotiations as threaded chats with offer movement and live system events.</p>
            </div>
            <div className="tomato-operator-item">
              <strong>Why it happened</strong>
              <p>Compare noisy market beliefs, private reasoning, reservation-price violations, and chain pressure.</p>
            </div>
            <div className="tomato-operator-item">
              <strong>What to change next</strong>
              <p>Use diagnosis cards, exports, and shocks to test different market narratives quickly.</p>
            </div>
          </div>
        </article>
      </section>
    </main>
  );
}
