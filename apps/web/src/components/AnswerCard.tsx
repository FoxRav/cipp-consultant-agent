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
        <span>{statusLabel(answer.answer_status)}</span>
        <span>{answer.duration_ms} ms</span>
        <span>lähdeperustainen</span>
      </div>
      <h2>Vastaus</h2>
      <p className="short-answer">{answer.short_answer}</p>
      <CostEstimate answer={answer} />
      <CaseUsed caseUsed={answer.case_used} />
      <ListBlock title="Keskeiset huomiot" values={answer.key_points} ordered />
      <ListBlock title="Kustannusajurit" values={answer.cost_drivers ?? []} />
      <ListBlock title="Tarkennettavat tiedot" values={answer.missing_information ?? []} />
      <ListBlock title="Lähteiden tukemat muistiinpanot" values={answer.source_based_notes} />
      <ListBlock title="Seuraavat tarkentavat kysymykset" values={answer.recommended_next_questions} />
    </section>
  );
}

function CostEstimate({ answer }: { answer: AnswerResponse }) {
  if (!answer.estimate_type) {
    return null;
  }
  if (answer.estimate_low == null || answer.estimate_high == null) {
    return (
      <div className="cost-estimate">
        <h3>Alustava kustannusarvio</h3>
        <p>Euromääräistä arviota ei voitu muodostaa nykyisestä lähdedatasta.</p>
      </div>
    );
  }
  return (
    <div className="cost-estimate">
      <h3>Alustava kustannusarvio</h3>
      <p>
        {formatAmount(answer.estimate_low)}-{formatAmount(answer.estimate_high)} {answer.estimate_currency ?? "EUR"}
      </p>
    </div>
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

function statusLabel(status: string) {
  if (status === "answered") return "vastattu";
  if (status === "partial") return "osittainen";
  if (status === "insufficient_evidence") return "ei riittävää näyttöä";
  return status;
}

function formatAmount(value: number | string) {
  const numeric = typeof value === "number" ? value : Number.parseInt(value, 10);
  if (!Number.isFinite(numeric)) return String(value);
  return numeric.toLocaleString("fi-FI");
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
