import Link from "next/link";

import { RunSeedForm } from "../components/run-seed-form";
import { getRuns } from "../lib/api";
import { formatDateTime, formatLabel } from "../lib/format";


const CHAIN_NODES = [
  {
    title: "Seller",
    symbol: "crate",
    tone: "leaf",
    metrics: [
      ["Offer Price", "$2.40/kg"],
      ["Margin", "18%"],
      ["Inventory", "High"],
    ],
  },
  {
    title: "Processor",
    symbol: "tank",
    tone: "red",
    metrics: [
      ["Target Cost", "$2.20/kg"],
      ["Capacity", "85%"],
      ["Risk", "Medium"],
    ],
  },
  {
    title: "Retailer",
    symbol: "tag",
    tone: "orange",
    metrics: [
      ["Shelf Price", "$4.99"],
      ["Demand", "Strong"],
      ["Stock", "Low"],
    ],
  },
  {
    title: "Market",
    symbol: "board",
    tone: "yellow",
    metrics: [
      ["Forecast", "+12%"],
      ["Pressure", "Hot"],
      ["Volatility", "7%"],
    ],
  },
];

const MARKET_CONDITIONS = [
  ["Harvest Quality", "87", "vine"],
  ["Packaging Cost", "42", "orange"],
  ["Retail Demand", "73", "red"],
  ["Weather Risk", "28", "steel"],
  ["Competitor Pricing", "61", "charcoal"],
  ["Shelf Demand", "79", "leaf"],
];

function TomatoMark() {
  return (
    <span className="tomato-mark" aria-hidden="true">
      <span className="tomato-mark-leaves" />
      <span className="tomato-mark-shine" />
    </span>
  );
}

function FlowGlyph({ symbol }: { symbol: string }) {
  return (
    <span className={`flow-glyph ${symbol}`} aria-hidden="true">
      <span />
    </span>
  );
}

export default async function HomePage() {
  const runsResult = await getRuns();
  const recentRuns = (runsResult.data ?? []).slice(0, 5);

  return (
    <main className="tomato-dashboard">
      <section className="tomato-command">
        <div className="tomato-seed-field" aria-hidden="true" />
        <div className="tomato-slice huge one" aria-hidden="true" />
        <div className="tomato-slice huge two" aria-hidden="true" />

        <div className="command-copy">
          <div className="brand-lockup">
            <TomatoMark />
            <span>Tomato Treaty</span>
          </div>
          <div className="eyebrow sauce-stamp">Market negotiation</div>
          <h1>Run a Tomato Supply Chain Negotiation</h1>
          <p>
            Seed the market, start the negotiation, and watch ketchup economics move
            from crate to shelf.
          </p>
          <div className="command-badges" aria-label="Simulation capabilities">
            <span className="tomato-chip vine">Ripe market feed</span>
            <span className="tomato-chip red">Cost spike ready</span>
            <span className="tomato-chip yellow">Trace live</span>
          </div>
        </div>

        <aside className="simulation-console" aria-label="Launch simulation">
          <div className="console-header">
            <div>
              <div className="eyebrow">Launch Simulation Batch</div>
              <h2>Open the sauce line</h2>
            </div>
          </div>
          <RunSeedForm mode="redirect" />
          <p className="console-note">
            Runs open in the analysis workspace with chat replay, price movement,
            belief divergence, and export logs.
          </p>
        </aside>
      </section>

      <section className="tomato-grid">
        <article className="tomato-panel supply-panel">
          <div className="panel-title-row">
            <div>
              <div className="eyebrow">Supply Chain Flow</div>
              <h2>Sauce pipes, vine pressure, and deal movement</h2>
            </div>
            <span className="tomato-chip vine">Crate to shelf</span>
          </div>

          <div className="supply-flow" aria-label="Seller to processor to retailer to market">
            {CHAIN_NODES.map((node, index) => (
              <div className="flow-step" key={node.title}>
                <article className={`flow-node ${node.tone}`}>
                  <div className="flow-node-head">
                    <FlowGlyph symbol={node.symbol} />
                    <h3>{node.title}</h3>
                  </div>
                  <dl className="metric-list">
                    {node.metrics.map(([label, value]) => (
                      <div key={label}>
                        <dt>{label}</dt>
                        <dd>{value}</dd>
                      </div>
                    ))}
                  </dl>
                </article>
                {index < CHAIN_NODES.length - 1 ? (
                  <div className="sauce-arrow" aria-hidden="true">
                    <span />
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </article>

        <aside className="tomato-panel pulse-panel">
          <div className="panel-title-row compact">
            <div>
              <div className="eyebrow">Negotiation Pulse</div>
              <h2>Batch pressure</h2>
            </div>
            <span className="tomato-chip yellow">Live</span>
          </div>

          <div className="pulse-stat-grid">
            <div>
              <span>Phase</span>
              <strong>Packaging Cost</strong>
            </div>
            <div>
              <span>Round</span>
              <strong>2 of 4</strong>
            </div>
          </div>

          <div className="stance-stack">
            <div><span>Seller stance</span><b className="tomato-chip red">Firm</b></div>
            <div><span>Manufacturer stance</span><b className="tomato-chip vine">Flexible</b></div>
            <div><span>Retail demand</span><b className="tomato-chip yellow">Rising</b></div>
          </div>

          <div className="offer-meter">
            <div><span>Current offer</span><strong>$1.42/unit</strong></div>
            <div className="ketchup-drip" aria-hidden="true" />
            <div><span>Counteroffer</span><strong>$1.36/unit</strong></div>
          </div>

          <div className="probability-meter">
            <div><span>Outcome probability</span><strong>68%</strong></div>
            <span className="meter-track"><span /></span>
          </div>
        </aside>
      </section>

      <section className="tomato-grid lower-grid">
        <article className="tomato-panel market-panel">
          <div className="panel-title-row">
            <div>
              <div className="eyebrow">Market Conditions</div>
              <h2>Tomato weather, shelf heat, and pricing drag</h2>
            </div>
          </div>
          <div className="gauge-grid">
            {MARKET_CONDITIONS.map(([label, value, tone]) => (
              <div className={`tomato-gauge ${tone}`} key={label}>
                <div className="gauge-top">
                  <span>{label}</span>
                  <strong>{value}%</strong>
                </div>
                <span className="gauge-track">
                  <span style={{ width: `${value}%` }} />
                </span>
              </div>
            ))}
          </div>
        </article>

        <article className="tomato-panel recent-panel">
          <div className="panel-title-row">
            <div>
              <div className="eyebrow">Recent Runs</div>
              <h2>Stamped crate records</h2>
            </div>
            <Link className="button secondary crate-button" href="/runs">
              View Runs
            </Link>
          </div>

          <div className="recent-run-table">
            {recentRuns.length > 0 ? (
              recentRuns.map((run) => (
                <Link className="recent-run-row" href={`/runs/${run.id}`} key={run.id}>
                  <span className="run-id">{run.id.slice(0, 12)}</span>
                  <span>{run.scenario}</span>
                  <span className={run.status === "completed" ? "tomato-chip vine" : run.status === "failed" ? "tomato-chip red" : "tomato-chip yellow"}>
                    {formatLabel(run.status)}
                  </span>
                  <span>{run.step_count} steps</span>
                  <span>{formatDateTime(run.updated_at)}</span>
                </Link>
              ))
            ) : (
              <div className="empty-crate">
                <TomatoMark />
                <h3>No tomatoes in the crate yet.</h3>
                <p>Run a simulation and the new record will appear here.</p>
              </div>
            )}
          </div>
        </article>
      </section>
    </main>
  );
}
