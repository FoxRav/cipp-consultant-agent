import type { AnswerResponse } from "../api/client";

type Props = {
  answer: AnswerResponse | null;
  loading: boolean;
};

export function AnswerCard({ answer, loading }: Props) {
  if (loading) {
    return <section className="answer-card muted">Muodostetaan lähdeperustaista vastausta...</section>;
  }
  if (!answer) {
    return (
      <section className="answer-card empty">
        <h2>Vastaus ilmestyy tähän</h2>
        <p>Syötä taloyhtiön perustiedot yläpalkkiin ja kysy urakan laajuudesta, maksueristä tai laadunvarmistuksesta.</p>
      </section>
    );
  }

  return (
    <section className="answer-card">
      <div className="answer-meta">
        <span>{answer.answer_status}</span>
        <span>{answer.duration_ms} ms</span>
        <span>{answer.generation_mode}</span>
      </div>
      <h2>Vastaus</h2>
      <p className="short-answer">{answer.short_answer}</p>
      <CaseUsed caseUsed={answer.case_used} />
      <ListBlock title="Keskeiset huomiot" values={answer.key_points} ordered />
      <ListBlock title="Kustannusajurit" values={answer.cost_drivers ?? []} />
      <ListBlock title="Tarkennettavat tiedot" values={answer.missing_information ?? []} />
      <ListBlock title="Lähteiden tukemat muistiinpanot" values={answer.source_based_notes} />
      <ListBlock title="Seuraavat tarkentavat kysymykset" values={answer.recommended_next_questions} />
    </section>
  );
}

function CaseUsed({ caseUsed }: { caseUsed?: Record<string, number | boolean | string | null> }) {
  if (!caseUsed) {
    return null;
  }
  const items: Array<[string, number | boolean | string | null | undefined]> = [
    ["Asuntoja", caseUsed.apartments_count],
    ["Rakennuksia", caseUsed.buildings_count],
    ["Porrashuoneita", caseUsed.staircases_count],
    ["JV-pystyviemäreitä", caseUsed.jv_verticals_count],
    ["SV-pystyviemäreitä", caseUsed.sv_verticals_count],
    ["Kattokaivot", caseUsed.roof_drains_count],
    ["Pohjaviemäri m", caseUsed.bottom_drain_length_m],
    ["Tonttilinja m", caseUsed.yard_line_length_m],
    ["Sadevesilinjat m", caseUsed.stormwater_line_length_m]
  ];
  return (
    <div className="case-used">
      <h3>Arviossa käytetty case</h3>
      <dl>
        {items.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value ?? "puuttuu"}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function ListBlock({ title, values, ordered = false }: { title: string; values: string[]; ordered?: boolean }) {
  if (!values.length) {
    return null;
  }
  const ListTag = ordered ? "ol" : "ul";
  return (
    <div className="list-block">
      <h3>{title}</h3>
      <ListTag>
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ListTag>
    </div>
  );
}
