import type { AuthAdapter } from "./types";

export function createSupabaseAuthAdapter(): AuthAdapter {
  const message =
    "Supabase auth adapter is planned but not enabled in this prototype. Use VITE_AUTH_PROVIDER=mock for local testing.";
  return {
    provider: "supabase",
    async getSession() {
      return null;
    },
    async signIn() {
      throw new Error(message);
    },
    async register() {
      throw new Error(message);
    },
    async signOut() {
      return undefined;
    }
  };
}

