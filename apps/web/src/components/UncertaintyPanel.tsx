type Props = {
  uncertainties: string[];
  missingFields: string[];
  warnings: string[];
};

export function UncertaintyPanel({ uncertainties, missingFields, warnings }: Props) {
  return (
    <section className="panel-card">
      <h2>Epävarmuudet</h2>
      <InfoList title="Puuttuvat tiedot" values={missingFields} />
      <InfoList title="Epävarmuudet" values={uncertainties} />
      <InfoList title="Varoitukset" values={warnings} />
    </section>
  );
}

function InfoList({ title, values }: { title: string; values: string[] }) {
  return (
    <div className="info-list">
      <h3>{title}</h3>
      {values.length ? (
        <ul>
          {values.map((value) => (
            <li key={value}>{value}</li>
          ))}
        </ul>
      ) : (
        <p className="muted-text">Ei merkintöjä.</p>
      )}
    </div>
  );
}
