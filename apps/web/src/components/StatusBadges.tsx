import type { AnswerResponse } from "../api/client";

type Props = {
  answer: AnswerResponse | null;
  llmEnabled: boolean;
  apiHealth: "checking" | "ok" | "offline" | "error";
};

export function StatusBadges({ answer, llmEnabled, apiHealth }: Props) {
  const hasExpertGuidance = Boolean(answer?.sources?.some((source) => source.source_class === "expert_guidance"));
  return (
    <div className="status-badges" aria-label="Tilamerkinnät">
      <span className={apiBadgeClass(apiHealth)}>API: {apiLabel(apiHealth)}</span>
      <span className={badgeClass(answer?.answer_status ?? "idle")}>{answerStatusLabel(answer?.answer_status)}</span>
      <span className={llmEnabled || answer?.llm_used ? "badge warn" : "badge ok"}>LLM ei käytössä</span>
      <span className="badge ok">lähdeperustainen</span>
      {hasExpertGuidance ? <span className="badge info">asiantuntijaohje</span> : null}
    </div>
  );
}

function apiLabel(status: "checking" | "ok" | "offline" | "error") {
  if (status === "checking") return "tarkistetaan";
  if (status === "ok") return "ok";
  if (status === "offline") return "ei yhteyttä";
  return "virhe";
}

function answerStatusLabel(status: string | undefined) {
  if (status === "answered") return "vastattu";
  if (status === "partial") return "osittainen";
  if (status === "insufficient_evidence") return "ei riittävää näyttöä";
  return "odottaa";
}

function apiBadgeClass(status: "checking" | "ok" | "offline" | "error") {
  if (status === "ok") {
    return "badge ok";
  }
  if (status === "checking") {
    return "badge neutral";
  }
  return "badge danger";
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
