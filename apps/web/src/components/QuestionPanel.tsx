type Props = {
  question: string;
  loading: boolean;
  showDebug: boolean;
  onQuestionChange: (value: string) => void;
  onSubmit: () => void;
  onDebugChange: (value: boolean) => void;
};

export function QuestionPanel({ question, loading, showDebug, onQuestionChange, onSubmit, onDebugChange }: Props) {
  return (
    <section className="question-panel">
      <label htmlFor="question">Kysy CIPP-/sukitusurakasta</label>
      <textarea
        id="question"
        value={question}
        onChange={(event) => onQuestionChange(event.target.value)}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
            onSubmit();
          }
        }}
      />
      <div className="question-actions">
        <label className="debug-toggle">
          <input type="checkbox" checked={showDebug} onChange={(event) => onDebugChange(event.target.checked)} />
          <span>Näytä tekninen paketti</span>
        </label>
        <button type="button" onClick={onSubmit} disabled={loading || !question.trim()}>
          {loading ? "Haetaan..." : "Lähetä"}
        </button>
      </div>
    </section>
  );
}
