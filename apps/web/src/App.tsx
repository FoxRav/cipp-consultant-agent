import { useEffect, useMemo, useState } from "react";
import { getAppConfig, getSuggestedQuestions, postAnswer, type AnswerResponse, type AppConfig, type SuggestedQuestion, type UserCase } from "./api/client";
import { AnswerCard } from "./components/AnswerCard";
import { QuestionPanel } from "./components/QuestionPanel";
import { SourcesPanel } from "./components/SourcesPanel";
import { StatusBadges } from "./components/StatusBadges";
import { SuggestedQuestions } from "./components/SuggestedQuestions";
import { TopCaseBar } from "./components/TopCaseBar";
import { UncertaintyPanel } from "./components/UncertaintyPanel";

const fallbackDefaults: UserCase = {
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
};

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [suggestions, setSuggestions] = useState<SuggestedQuestion[]>([]);
  const [userCase, setUserCase] = useState<UserCase>(fallbackDefaults);
  const [question, setQuestion] = useState("Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?");
  const [showDebug, setShowDebug] = useState(false);
  const [answer, setAnswer] = useState<AnswerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([getAppConfig(), getSuggestedQuestions()])
      .then(([appConfig, fetchedSuggestions]) => {
        setConfig(appConfig);
        setUserCase({ ...fallbackDefaults, ...appConfig.defaults });
        setSuggestions(fetchedSuggestions);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "API-yhteys epäonnistui.");
      });
  }, []);

  const fields = useMemo(() => config?.user_case_fields ?? [], [config]);
  const defaults = useMemo(() => ({ ...fallbackDefaults, ...(config?.defaults ?? {}) }), [config]);

  async function submit(nextQuestion = question) {
    if (!nextQuestion.trim()) {
      return;
    }
    setQuestion(nextQuestion);
    setLoading(true);
    setError(null);
    try {
      setAnswer(await postAnswer(nextQuestion, userCase, showDebug));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Vastauksen muodostus epäonnistui.");
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
        <StatusBadges answer={answer} llmEnabled={config?.llm_enabled ?? false} />
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
          {error ? <div className="error-box">{error}</div> : null}
          <AnswerCard answer={answer} loading={loading} />
        </div>

        <aside className="side-panel">
          <SourcesPanel sources={answer?.sources ?? []} />
          <UncertaintyPanel
            uncertainties={answer?.uncertainties ?? []}
            missingFields={answer?.missing_user_case_fields ?? []}
            warnings={answer?.warnings ?? []}
          />
          {showDebug && answer ? (
            <details className="debug-panel">
              <summary>Show debug packet</summary>
              <pre>{JSON.stringify({ debug: answer.debug, retrieval_packet: answer.retrieval_packet }, null, 2)}</pre>
            </details>
          ) : null}
        </aside>
      </section>
    </main>
  );
}
