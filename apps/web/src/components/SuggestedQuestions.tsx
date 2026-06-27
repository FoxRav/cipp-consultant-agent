import type { SuggestedQuestion } from "../api/client";

type Props = {
  suggestions: SuggestedQuestion[];
  onSelect: (question: SuggestedQuestion) => void;
};

export function SuggestedQuestions({ suggestions, onSelect }: Props) {
  if (!suggestions.length) {
    return null;
  }
  return (
    <section className="suggestions" aria-label="Ehdotetut kysymykset">
      {suggestions.map((item) => (
        <button key={item.topic_code} type="button" onClick={() => onSelect(item)}>
          {item.label}
        </button>
      ))}
    </section>
  );
}
