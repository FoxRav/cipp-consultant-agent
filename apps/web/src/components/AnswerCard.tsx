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
      <ListBlock title="Keskeiset huomiot" values={answer.key_points} ordered />
      <ListBlock title="Lähteiden tukemat muistiinpanot" values={answer.source_based_notes} />
      <ListBlock title="Seuraavat tarkentavat kysymykset" values={answer.recommended_next_questions} />
    </section>
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
