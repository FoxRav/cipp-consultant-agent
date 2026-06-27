import { useEffect, useMemo, useState } from "react";
import {
  ApiClientError,
  apiBaseUrlLabel,
  getAppConfig,
  getHealth,
  getSuggestedQuestions,
  postAnswer,
  type ApiErrorDetails,
  type AnswerResponse,
  type AppConfig,
  type SuggestedQuestion,
  type UserCase
} from "./api/client";
import { createAuthAdapter } from "./auth/authAdapter";
import type { AuthSession } from "./auth/types";
import { AnswerCard } from "./components/AnswerCard";
import { AuthPanel } from "./components/AuthPanel";
import { QuestionPanel } from "./components/QuestionPanel";
import { StatusBadges } from "./components/StatusBadges";
import { SuggestedQuestions } from "./components/SuggestedQuestions";
import { TopCaseBar } from "./components/TopCaseBar";
import {
  DEFAULT_USER_CASE,
  loadInitialUserCase,
  normalizeUserCase,
  persistUserCase,
  visibleUserCaseFields
} from "./config/defaultCase";

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [suggestions, setSuggestions] = useState<SuggestedQuestion[]>([]);
  const [userCase, setUserCaseState] = useState<UserCase>(() => loadInitialUserCase());
  const [question, setQuestion] = useState("Kuinka paljon yllä asetettu taloyhtiön sukitusurakka maksaa?");
  const [showDebug, setShowDebug] = useState(false);
  const [answer, setAnswer] = useState<AnswerResponse | null>(null);
  const [session, setSession] = useState<AuthSession | null>(null);
  const [apiHealth, setApiHealth] = useState<"checking" | "ok" | "offline" | "error">("checking");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<ApiErrorDetails | null>(null);
  const authAdapter = useMemo(() => createAuthAdapter(), []);

  useEffect(() => {
    void getHealth()
      .then(() => setApiHealth("ok"))
      .catch((err: unknown) => {
        setApiHealth(err instanceof ApiClientError ? "offline" : "error");
      });
    void Promise.all([getAppConfig(), getSuggestedQuestions()])
      .then(([appConfig, fetchedSuggestions]) => {
        setConfig(appConfig);
        setUserCase(normalizeUserCase({ ...DEFAULT_USER_CASE, ...appConfig.defaults, ...loadInitialUserCase() }));
        setSuggestions(fetchedSuggestions);
      })
      .catch((err: unknown) => {
        setError(formatError(err));
        setErrorDetails(err instanceof ApiClientError ? err.details : null);
      });
  }, []);

  useEffect(() => {
    void authAdapter.getSession().then(setSession).catch(() => setSession(null));
  }, [authAdapter]);

  const fields = useMemo(() => visibleUserCaseFields(config?.user_case_fields ?? []), [config]);
  const defaults = useMemo(() => normalizeUserCase({ ...DEFAULT_USER_CASE, ...(config?.defaults ?? {}) }), [config]);

  function setUserCase(nextUserCase: UserCase) {
    const normalized = normalizeUserCase(nextUserCase);
    setUserCaseState(normalized);
    persistUserCase(normalized);
  }

  async function submit(nextQuestion = question) {
    if (!nextQuestion.trim()) {
      return;
    }
    setQuestion(nextQuestion);
    setLoading(true);
    setError(null);
    setErrorDetails(null);
    try {
      setAnswer(await postAnswer(nextQuestion, userCase, showDebug, session?.accessToken));
      setApiHealth("ok");
    } catch (err) {
      setError(formatError(err));
      setErrorDetails(err instanceof ApiClientError ? err.details : null);
      setApiHealth(err instanceof ApiClientError && !err.details.status ? "offline" : "error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="hero-bar">
        <div>
          <p className="eyebrow">Local dev playground</p>
          <h1>CIPP Consultant Agent</h1>
        </div>
        <div className="hero-actions">
          <StatusBadges answer={answer} llmEnabled={config?.llm_enabled ?? false} apiHealth={apiHealth} />
          <AuthPanel adapter={authAdapter} session={session} onSessionChange={setSession} />
        </div>
      </header>

      <TopCaseBar fields={fields} userCase={userCase} onChange={setUserCase} onReset={() => setUserCase(defaults)} />

      <section className="workspace">
        <div className="conversation">
          <QuestionPanel
            question={question}
            loading={loading}
            showDebug={showDebug}
            onQuestionChange={setQuestion}
            onSubmit={() => void submit()}
            onDebugChange={setShowDebug}
          />
          <SuggestedQuestions suggestions={suggestions} onSelect={(item) => void submit(item.question)} />
          {error ? (
            <div className="error-box">
              <pre>{error}</pre>
              {showDebug && errorDetails ? (
                <details>
                  <summary>API error details</summary>
                  <pre>{JSON.stringify(errorDetails, null, 2)}</pre>
                </details>
              ) : null}
            </div>
          ) : null}
          <AnswerCard answer={answer} loading={loading} />
          {showDebug && answer ? (
            <details className="debug-panel">
              <summary>Show debug packet</summary>
              <pre>{JSON.stringify({ debug: answer.debug, retrieval_packet: answer.retrieval_packet }, null, 2)}</pre>
            </details>
          ) : null}
        </div>
      </section>
    </main>
  );
}

function formatError(err: unknown): string {
  if (err instanceof ApiClientError) {
    return err.message;
  }
  if (err instanceof Error) {
    return [
      "Sovelluksessa tapahtui virhe.",
      err.message,
      "",
      `API base URL: ${apiBaseUrlLabel()}`
    ].join("\n");
  }
  return "Tuntematon virhe.";
}
