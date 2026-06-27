export type AuthProvider = "mock" | "supabase";

export type AuthUser = {
  id: string;
  email: string;
  displayName?: string;
};

export type AuthSession = {
  accessToken: string;
  user: AuthUser;
  provider: AuthProvider;
  expiresAt: string;
};

export type AuthCredentials = {
  email: string;
  password: string;
};

export type AuthAdapter = {
  provider: AuthProvider;
  getSession: () => Promise<AuthSession | null>;
  signIn: (credentials: AuthCredentials) => Promise<AuthSession>;
  register: (credentials: AuthCredentials) => Promise<AuthSession>;
  signOut: () => Promise<void>;
};

