import type { Source } from "../api/client";

type Props = {
  sources: Source[];
};

export function SourcesPanel({ sources }: Props) {
  return (
    <section className="panel-card">
      <h2>Lähteet</h2>
      {!sources.length ? <p className="muted-text">Ei vielä lähteitä.</p> : null}
      <div className="source-list">
        {sources.map((source, index) => (
          <article className="source-item" key={`${source.anonymized_reference_label}-${source.locator}-${index}`}>
            <div className="source-topline">
              <strong>{source.anonymized_reference_label}</strong>
              <span>{source.text_context_status}</span>
            </div>
            <p className="source-type">
              {source.document_type} / {source.source_class}
            </p>
            <p>{source.snippet}</p>
            <div className="source-confidence">confidence: {source.confidence ?? "n/a"}</div>
          </article>
        ))}
      </div>
    </section>
  );
}
