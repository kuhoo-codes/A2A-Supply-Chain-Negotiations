type HealthStatusProps = {
  status: string | null;
  error: string | null;
};


export function HealthStatus({ status, error }: HealthStatusProps) {
  const toneClass = error ? "badge danger" : "badge";
  const text = error ? "Unavailable" : status === "ok" ? "Healthy" : "Unknown";

  return (
    <div className="status-row">
      <div>
        <div className="eyebrow">Backend Health</div>
        <p className="muted-copy">
          {error ?? "FastAPI health check is reachable from the frontend."}
        </p>
      </div>
      <span className={toneClass}>{text}</span>
    </div>
  );
}
