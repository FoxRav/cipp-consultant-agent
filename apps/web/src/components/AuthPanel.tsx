import { useState } from "react";
import type { AuthAdapter, AuthSession } from "../auth/types";

type Props = {
  adapter: AuthAdapter;
  session: AuthSession | null;
  onSessionChange: (session: AuthSession | null) => void;
};

export function AuthPanel({ adapter, session, onSessionChange }: Props) {
  const [email, setEmail] = useState("demo@example.test");
  const [password, setPassword] = useState("local-password");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit() {
    setLoading(true);
    setError(null);
    try {
      const nextSession =
        mode === "login"
          ? await adapter.signIn({ email, password })
          : await adapter.register({ email, password });
      onSessionChange(nextSession);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kirjautuminen epäonnistui.");
    } finally {
      setLoading(false);
    }
  }

  async function logout() {
    await adapter.signOut();
    onSessionChange(null);
  }

  return (
    <section className="auth-panel" aria-label="Kirjautumisen prototyyppi">
      <div>
        <p className="panel-label">Kirjautumisen prototyyppi</p>
        <strong>{adapter.provider === "mock" ? "Testikirjautuminen" : "Supabase suunnitteilla"}</strong>
      </div>
      {session ? (
        <div className="auth-session">
          <span>{session.user.email}</span>
          <button type="button" onClick={() => void logout()}>
            Kirjaudu ulos
          </button>
        </div>
      ) : (
        <div className="auth-form">
          <select value={mode} onChange={(event) => setMode(event.target.value as "login" | "register")}>
            <option value="login">Kirjaudu</option>
            <option value="register">Rekisteröidy</option>
          </select>
          <input aria-label="Sähköposti" value={email} onChange={(event) => setEmail(event.target.value)} />
          <input
            aria-label="Salasana"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <button type="button" disabled={loading || !email || !password} onClick={() => void submit()}>
            {loading ? "Käsitellään..." : mode === "login" ? "Kirjaudu" : "Rekisteröidy"}
          </button>
        </div>
      )}
      {error ? <p className="auth-error">{error}</p> : null}
    </section>
  );
}
