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
const USE_MOCK_API =
  import.meta.env.VITE_USE_MOCK_API === "true" ||
  (typeof window !== "undefined" && new URLSearchParams(window.location.search).get("mock") === "1");

export async function getAppConfig(): Promise<AppConfig> {
  if (USE_MOCK_API) {
    return mockAppConfig();
  }
  const response = await fetch(`${API_BASE_URL}/api/app-config`);
  return assertJson(response);
}

export async function getSuggestedQuestions(): Promise<SuggestedQuestion[]> {
  if (USE_MOCK_API) {
    return mockSuggestedQuestions();
  }
  const response = await fetch(`${API_BASE_URL}/api/suggested-questions`);
  const body = await assertJson<{ questions: SuggestedQuestion[] }>(response);
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
  const response = await fetch(`${API_BASE_URL}/api/answer`, {
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
  return assertJson(response);
}

async function assertJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
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
      { name: "stormwater_line_length_m", label: "Sadevesilinjat m", type: "number", default: 30 },
      { name: "includes_video_inspection", label: "Videotarkastus", type: "boolean", default: true },
      { name: "includes_unit_prices", label: "Yksikköhinnat / lisätyöt", type: "boolean", default: true }
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
      topic_code: "video_inspection",
      label: "Videotarkastus",
      question: "Mitä videotarkastuksesta ja loppukuvauksesta pitää vaatia?"
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
  const response: AnswerResponse = {
    api_status: "ok",
    request_id: "mock-request-001",
    duration_ms: 80,
    question,
    answer_status: "answered",
    short_answer:
      "Mock-tila muodostaa turvallisen esimerkkivastauksen: tarkista urakan laajuus, maksuerien hyväksyntä, videotarkastus ja puuttuvat kohdetiedot ennen tarjouspyyntöä.",
    key_points: [
      `Kohteessa on testiarvona ${userCase.apartments_count} asuntoa, ${userCase.jv_verticals_count} JV-pystyviemäriä, ${userCase.sv_verticals_count} SV-pystyviemäriä ja ${userCase.roof_drains_count} kattokaivoa.`,
      "Pohjaviemärin ja tonttilinjan kuuluminen urakkaan kannattaa kirjata erikseen.",
      "Videotarkastus ja valvojan kommentit kannattaa sitoa vastaanottoon ja takuuajan seurantaan."
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
      "Miten videotarkastuksen hyväksyntä kirjataan vastaanottoon?"
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
    llm_used: false
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
