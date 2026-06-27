export type UserCase = {
  apartments_count: number;
  buildings_count: number;
  staircases_count: number;
  jv_verticals_count: number;
  sv_verticals_count: number;
  roof_drains_count: number;
  bottom_drain_length_m: number;
  yard_line_length_m: number;
  stormwater_line_length_m: number;
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
  case_used?: Record<string, number | boolean | string | null>;
  cost_drivers?: string[];
  missing_information?: string[];
  estimate_type?: string;
  retrieval_packet?: unknown;
  debug?: unknown;
};

export type HealthResponse = {
  status: string;
  service: string;
  llm_enabled: boolean;
};

export type ApiErrorDetails = {
  apiBaseUrl: string;
  endpoint: string;
  method: string;
  status?: number;
  responseBody?: string;
  cause?: string;
};

export class ApiClientError extends Error {
  details: ApiErrorDetails;

  constructor(message: string, details: ApiErrorDetails) {
    super(message);
    this.name = "ApiClientError";
    this.details = details;
  }
}

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

const configuredApiBaseUrl =
  typeof window !== "undefined"
    ? new URLSearchParams(window.location.search).get("apiBase")
    : undefined;
const API_BASE_URL = normalizeApiBaseUrl(configuredApiBaseUrl ?? import.meta.env.VITE_API_BASE_URL ?? "");
const USE_MOCK_API =
  import.meta.env.VITE_USE_MOCK_API === "true" ||
  (typeof window !== "undefined" && new URLSearchParams(window.location.search).get("mock") === "1");

export function apiBaseUrlLabel(): string {
  return API_BASE_URL || "same-origin Vite proxy";
}

export async function getHealth(): Promise<HealthResponse> {
  if (USE_MOCK_API) {
    return { status: "ok", service: "cipp-consultant-agent-dev-api-mock", llm_enabled: false };
  }
  return apiFetchJson<HealthResponse>("/api/health", { method: "GET" });
}

export async function getAppConfig(): Promise<AppConfig> {
  if (USE_MOCK_API) {
    return mockAppConfig();
  }
  return apiFetchJson<AppConfig>("/api/app-config", { method: "GET" });
}

export async function getSuggestedQuestions(): Promise<SuggestedQuestion[]> {
  if (USE_MOCK_API) {
    return mockSuggestedQuestions();
  }
  const body = await apiFetchJson<{ questions: SuggestedQuestion[] }>("/api/suggested-questions", { method: "GET" });
  return body.questions;
}

export async function postAnswer(
  question: string,
  userCase: UserCase,
  includeDebug: boolean,
  accessToken?: string
): Promise<AnswerResponse> {
  if (USE_MOCK_API) {
    return mockAnswer(question, userCase, includeDebug);
  }
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  return apiFetchJson<AnswerResponse>("/api/answer", {
    method: "POST",
    headers,
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
}

async function apiFetchJson<T>(endpoint: string, init: RequestInit & { method: string }): Promise<T> {
  const url = buildApiUrl(endpoint);
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (err) {
    throw new ApiClientError(
      [
        "API-yhteys epäonnistui.",
        "Tarkista että backend on käynnissä:",
        "cipp-run-dev-api --host 127.0.0.1 --port 8000",
        "",
        `API base URL: ${apiBaseUrlLabel()}`,
        `Endpoint: ${endpoint}`,
        "Pyyntö ei lähtenyt perille tai selain esti sen. Todennäköinen syy on backend offline, väärä portti tai CORS/fetch-ongelma."
      ].join("\n"),
      {
        apiBaseUrl: apiBaseUrlLabel(),
        endpoint,
        method: init.method,
        cause: err instanceof Error ? err.message : String(err)
      }
    );
  }
  return assertJson(response, endpoint, init.method);
}

async function assertJson<T>(response: Response, endpoint: string, method: string): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new ApiClientError(
      [
        "API palautti virheen.",
        `HTTP status: ${response.status}`,
        `API base URL: ${apiBaseUrlLabel()}`,
        `Endpoint: ${endpoint}`,
        text ? `Response body: ${text.slice(0, 800)}` : "Response body: empty"
      ].join("\n"),
      {
        apiBaseUrl: apiBaseUrlLabel(),
        endpoint,
        method,
        status: response.status,
        responseBody: text
      }
    );
  }
  return (await response.json()) as T;
}

function normalizeApiBaseUrl(value: string): string {
  return value.trim().replace(/\/+$/g, "");
}

function buildApiUrl(endpoint: string): string {
  if (!API_BASE_URL) {
    return endpoint;
  }
  return `${API_BASE_URL}${endpoint}`;
}

function mockAppConfig(): AppConfig {
  return {
    environment: "local_dev_mock",
    llm_enabled: false,
    defaults: {
      apartments_count: 30,
      buildings_count: 1,
      staircases_count: 3,
      jv_verticals_count: 15,
      sv_verticals_count: 4,
      roof_drains_count: 4,
      bottom_drain_length_m: 50,
      yard_line_length_m: 30,
      stormwater_line_length_m: 30,
      includes_bottom_drain: true,
      includes_yard_line: false,
      includes_stormwater: false,
      includes_roof_drains: false,
      includes_video_inspection: true,
      includes_unit_prices: true
    },
    user_case_fields: [
      { name: "apartments_count", label: "Asuntoja", type: "number", default: 30 },
      { name: "buildings_count", label: "Rakennuksia", type: "number", default: 1 },
      { name: "staircases_count", label: "Porrashuoneita", type: "number", default: 3 },
      { name: "jv_verticals_count", label: "JV-pystyviemäreitä", type: "number", default: 15 },
      { name: "sv_verticals_count", label: "SV-pystyviemäreitä", type: "number", default: 4 },
      { name: "roof_drains_count", label: "Kattokaivot", type: "number", default: 4 },
      { name: "bottom_drain_length_m", label: "Pohjaviemäri m", type: "number", default: 50 },
      { name: "yard_line_length_m", label: "Tonttilinja m", type: "number", default: 30 },
      { name: "stormwater_line_length_m", label: "Sadevesilinjat m", type: "number", default: 30 }
    ],
    topics: mockSuggestedQuestions().map((question) => ({
      topic_code: question.topic_code,
      label: question.label
    })),
    ui_labels: {
      answered: "Answered",
      partial: "Partial",
      insufficient_evidence: "Insufficient evidence",
      llm_used: "LLM used",
      expert_guidance: "Expert guidance",
      source_grounded: "Source grounded"
    }
  };
}

function mockSuggestedQuestions(): SuggestedQuestion[] {
  return [
    {
      topic_code: "payment",
      label: "Maksuerät",
      question: "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?"
    },
    {
      topic_code: "wastewater_scope",
      label: "JV ja pohjaviemäri",
      question: "Mitä pitää huomioida taloyhtiön JV-pystylinjojen ja pohjaviemärin sukituksessa?"
    },
    {
      topic_code: "boundaries",
      label: "Urakkarajat",
      question: "Mitä urakkarajoissa pitää huomioida?"
    },
    {
      topic_code: "amateur_operator_guidance",
      label: "Muistilista",
      question: "Mitä amatööritoimijan pitää ymmärtää ennen kuin taloyhtiö pyytää urakkatarjouksia?"
    }
  ];
}

async function mockAnswer(question: string, userCase: UserCase, includeDebug: boolean): Promise<AnswerResponse> {
  await new Promise((resolve) => window.setTimeout(resolve, 80));
  const isCostQuestion = /paljonko|hinta|kustannus|maksaa/i.test(question);
  const response: AnswerResponse = {
    api_status: "ok",
    request_id: "mock-request-001",
    duration_ms: 80,
    question,
    answer_status: "answered",
    short_answer:
      "Mock-tila muodostaa turvallisen esimerkkivastauksen: tarkista urakan laajuus, maksuerien hyväksyntä ja puuttuvat kohdetiedot ennen tarjouspyyntöä.",
    key_points: [
      `Kohteessa on testiarvona ${userCase.apartments_count} asuntoa, ${userCase.jv_verticals_count} JV-pystyviemäriä, ${userCase.sv_verticals_count} SV-pystyviemäriä ja ${userCase.roof_drains_count} kattokaivoa.`,
      "Pohjaviemärin ja tonttilinjan kuuluminen urakkaan kannattaa kirjata erikseen.",
      "Laadunvarmistus ja valvojan kommentit kannattaa sitoa vastaanottoon ja takuuajan seurantaan."
    ],
    source_based_notes: [
      "Mock-lähdekatkelma (reference_001 / rfq / direct_section): laajuus ja laadunvarmistus kuvataan anonymisoidusti.",
      "Mock-lähdekatkelma (reference_002 / expert_guidance / direct_section): asiantuntijaohje tukee hallituksen valmistelun tarkistuslistaa."
    ],
    missing_user_case_fields: userCase.includes_yard_line ? [] : ["includes_yard_line"],
    uncertainties: [
      "Tarkka kohdekohtainen tulkinta edellyttää tarjouspyynnön ja sopimusasiakirjojen varmistusta.",
      "Mock-tila ei käytä tietokantaa eikä korvaa live API -testausta."
    ],
    recommended_next_questions: [
      "Kuuluuko tonttilinja urakkaan?",
      "Onko sadevesi mukana vain pihalla vai myös kattokaivojen kautta?",
      "Miten laadunvarmistuksen hyväksyntä kirjataan vastaanottoon?"
    ],
    sources: [
      {
        anonymized_reference_label: "reference_001",
        document_type: "rfq",
        source_type: "section",
        source_class: "retrieval_evidence",
        text_context_status: "direct_section",
        confidence: 1,
        snippet:
          "Anonymisoitu mock-katkelma kertoo, että JV-laajuus, pohjaviemäri ja laadunvarmistus pitää määritellä tarjouspyynnössä.",
        locator: "section",
        source_strength: "direct"
      },
      {
        anonymized_reference_label: "reference_002",
        document_type: "expert_guidance",
        source_type: "section",
        source_class: "expert_guidance",
        text_context_status: "direct_section",
        confidence: 0.9,
        snippet:
          "Asiantuntijaohjeen mock-katkelma tukee hankesuunnittelun, osakasviestinnän ja vastaanoton tarkistuslistaa.",
        locator: "section",
        source_strength: "direct"
      }
    ],
    warnings: [],
    generation_mode: "deterministic_source_grounded_mock",
    llm_used: false,
    ...(isCostQuestion
      ? {
          case_used: userCase,
          cost_drivers: [
            "Asuntojen määrä, pystylinjat ja linjapituudet ovat mock-tilan näkyvät kustannusajurit.",
            "Euromääräistä arviota ei muodosteta mock-tilassa."
          ],
          missing_information: ["urakkarajat", "todelliset linjapituudet", "suunnitelmien taso"]
        }
      : {})
  };
  if (includeDebug) {
    response.debug = {
      mock_api: true,
      received_user_case: userCase,
      retrieval_status: "ok",
      evidence_coverage_status: "ok"
    };
    response.retrieval_packet = {
      mode: "mock",
      reference_usage: { mode: "internal_anonymized_grounding", reference_projects_used: ["reference_001"] },
      detected_topics: ["wastewater_sewer", "quality_video"]
    };
  }
  return response;
}
