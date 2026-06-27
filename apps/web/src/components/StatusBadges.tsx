import type { AnswerResponse } from "../api/client";

type Props = {
  answer: AnswerResponse | null;
  llmEnabled: boolean;
};

export function StatusBadges({ answer, llmEnabled }: Props) {
  const hasExpertGuidance = Boolean(answer?.sources?.some((source) => source.source_class === "expert_guidance"));
  return (
    <div className="status-badges" aria-label="Tilamerkinnät">
      <span className={badgeClass(answer?.answer_status ?? "idle")}>{answer?.answer_status ?? "idle"}</span>
      <span className={llmEnabled || answer?.llm_used ? "badge warn" : "badge ok"}>llm_used=false</span>
      <span className="badge ok">source_grounded</span>
      {hasExpertGuidance ? <span className="badge info">expert_guidance</span> : null}
    </div>
  );
}

function badgeClass(status: string) {
  if (status === "answered") {
    return "badge ok";
  }
  if (status === "partial") {
    return "badge warn";
  }
  if (status === "insufficient_evidence") {
    return "badge danger";
  }
  return "badge neutral";
}
