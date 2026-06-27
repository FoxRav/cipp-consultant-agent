export type UserCase = {
  apartments_count: number;
  buildings_count: number;
  staircases_count: number;
  jv_verticals_count: number;
  sv_verticals_count: number;
  includes_bottom_drain: boolean;
  includes_yard_line: boolean;
  includes_stormwater: boolean;
  includes_roof_drains: boolean;
  includes_video_inspection: boolean;
  includes_unit_prices: boolean;
};

export type SuggestedQuestion = {
  topic_code: string;
  label: string;
  question: string;
};

export type Source = {
  anonymized_reference_label: string;
  document_type: string;
  source_type: string;
  source_class: string;
  text_context_status: string;
  confidence?: number | string | null;
  snippet: string;
  locator?: string;
  source_strength?: string;
};

export type AnswerResponse = {
  api_status: string;
  request_id: string;
  duration_ms: number;
  question: string;
  answer_status: "answered" | "partial" | "insufficient_evidence";
  short_answer: string;
  key_points: string[];
  source_based_notes: string[];
  missing_user_case_fields: string[];
  uncertainties: string[];
  recommended_next_questions: string[];
  sources: Source[];
  warnings: string[];
  generation_mode: string;
  llm_used: boolean;
  retrieval_packet?: unknown;
  debug?: unknown;
};

export type AppConfig = {
  environment: string;
  llm_enabled: boolean;
  user_case_fields: Array<{
    name: keyof UserCase;
    label: string;
    type: "number" | "boolean";
    default: number | boolean;
  }>;
  defaults: UserCase;
  topics: Array<{ topic_code: string; label: string }>;
  ui_labels: Record<string, string>;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function getAppConfig(): Promise<AppConfig> {
  const response = await fetch(`${API_BASE_URL}/api/app-config`);
  return assertJson(response);
}

export async function getSuggestedQuestions(): Promise<SuggestedQuestion[]> {
  const response = await fetch(`${API_BASE_URL}/api/suggested-questions`);
  const body = await assertJson<{ questions: SuggestedQuestion[] }>(response);
  return body.questions;
}

export async function postAnswer(
  question: string,
  userCase: UserCase,
  includeDebug: boolean
): Promise<AnswerResponse> {
  const response = await fetch(`${API_BASE_URL}/api/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      user_case: userCase,
      options: {
        max_sources: 8,
        include_retrieval_packet: includeDebug,
        include_debug: includeDebug
      }
    })
  });
  return assertJson(response);
}

async function assertJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}
