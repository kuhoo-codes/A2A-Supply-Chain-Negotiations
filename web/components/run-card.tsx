import Link from "next/link";

import { RunSummary } from "../lib/api-types";
import { formatDateTime, formatLabel } from "../lib/format";


type RunCardProps = {
  run: RunSummary;
};


export function RunCard({ run }: RunCardProps) {
  return (
    <Link className="run-card" href={`/runs/${run.id}`}>
      <div className="run-card-header">
        <h2>{run.title}</h2>
        <span className="badge">{formatLabel(run.status)}</span>
      </div>
      <p>{run.scenario}</p>
      <div className="run-meta">
        <span>{formatDateTime(run.updated_at)}</span>
        <span>{run.agent_count} agents</span>
        <span>{run.step_count} steps</span>
        <span>{formatLabel(run.current_phase)}</span>
      </div>
    </Link>
  );
}
