import { createMockAuthAdapter } from "./mockAuthAdapter";
import { createSupabaseAuthAdapter } from "./supabaseAuthAdapter";
import type { AuthAdapter, AuthProvider } from "./types";

export function createAuthAdapter(): AuthAdapter {
  const provider = (import.meta.env.VITE_AUTH_PROVIDER ?? "mock") as AuthProvider;
  if (provider === "supabase") {
    return createSupabaseAuthAdapter();
  }
  return createMockAuthAdapter();
}

