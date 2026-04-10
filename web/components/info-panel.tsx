type InfoPanelProps = {
  title: string;
  description: string;
};


export function InfoPanel({ title, description }: InfoPanelProps) {
  return (
    <article className="card">
      <div className="eyebrow">{title}</div>
      <p>{description}</p>
    </article>
  );
}
