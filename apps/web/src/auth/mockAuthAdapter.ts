import type { AuthAdapter, AuthCredentials, AuthSession } from "./types";

const STORAGE_KEY = "cipp_mock_auth_session";

export function createMockAuthAdapter(): AuthAdapter {
  return {
    provider: "mock",
    async getSession() {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return null;
      }
      return JSON.parse(raw) as AuthSession;
    },
    async signIn(credentials) {
      return saveMockSession(credentials);
    },
    async register(credentials) {
      return saveMockSession(credentials);
    },
    async signOut() {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  };
}

function saveMockSession(credentials: AuthCredentials): AuthSession {
  const normalizedEmail = credentials.email.trim().toLowerCase();
  const session: AuthSession = {
    accessToken: `mock.jwt.${btoa(normalizedEmail).replace(/=+$/g, "")}`,
    provider: "mock",
    expiresAt: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
    user: {
      id: `mock-user-${hashEmail(normalizedEmail)}`,
      email: normalizedEmail,
      displayName: normalizedEmail.split("@")[0]
    }
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  return session;
}

function hashEmail(value: string): string {
  let hash = 0;
  for (const char of value) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  }
  return hash.toString(16);
}

