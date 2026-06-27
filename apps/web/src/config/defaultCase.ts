export const CASE_SCHEMA_VERSION = 2;
export const USER_CASE_STORAGE_KEY = "cipp_user_case";
export const USER_CASE_SCHEMA_VERSION_KEY = "cipp_user_case_schema_version";

export const VISIBLE_CASE_FIELDS = [
  "apartments_count",
  "buildings_count",
  "staircases_count",
  "jv_verticals_count",
  "sv_verticals_count",
  "roof_drains_count",
  "bottom_drain_length_m",
  "yard_line_length_m",
  "stormwater_line_length_m"
] as const;

export type VisibleUserCaseFieldName = (typeof VISIBLE_CASE_FIELDS)[number];

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
};

export type UserCaseFieldConfig = {
  name: VisibleUserCaseFieldName;
  label: string;
  type: "number";
  default: number;
};

export const DEFAULT_USER_CASE = {
  apartments_count: 30,
  buildings_count: 1,
  staircases_count: 3,
  jv_verticals_count: 15,
  sv_verticals_count: 4,
  roof_drains_count: 4,
  bottom_drain_length_m: 50,
  yard_line_length_m: 30,
  stormwater_line_length_m: 30
};

export const USER_CASE_FIELDS: UserCaseFieldConfig[] = [
  { name: "apartments_count", label: "Asuntoja", type: "number", default: DEFAULT_USER_CASE.apartments_count },
  { name: "buildings_count", label: "Rakennuksia", type: "number", default: DEFAULT_USER_CASE.buildings_count },
  { name: "staircases_count", label: "Porrashuoneita", type: "number", default: DEFAULT_USER_CASE.staircases_count },
  {
    name: "jv_verticals_count",
    label: "JV-pystyviemäreitä",
    type: "number",
    default: DEFAULT_USER_CASE.jv_verticals_count
  },
  {
    name: "sv_verticals_count",
    label: "SV-pystyviemäreitä",
    type: "number",
    default: DEFAULT_USER_CASE.sv_verticals_count
  },
  { name: "roof_drains_count", label: "Kattokaivot", type: "number", default: DEFAULT_USER_CASE.roof_drains_count },
  {
    name: "bottom_drain_length_m",
    label: "Pohjaviemäri m",
    type: "number",
    default: DEFAULT_USER_CASE.bottom_drain_length_m
  },
  { name: "yard_line_length_m", label: "Tonttilinja m", type: "number", default: DEFAULT_USER_CASE.yard_line_length_m },
  {
    name: "stormwater_line_length_m",
    label: "Sadevesilinjat m",
    type: "number",
    default: DEFAULT_USER_CASE.stormwater_line_length_m
  }
];

const VISIBLE_USER_CASE_FIELD_NAMES = new Set<string>(USER_CASE_FIELDS.map((field) => field.name));

export function visibleUserCaseFields(fields: UserCaseFieldConfig[]): UserCaseFieldConfig[] {
  return fields.filter((field) => VISIBLE_USER_CASE_FIELD_NAMES.has(String(field.name)));
}

export function loadInitialUserCase(): UserCase {
  if (typeof window === "undefined") {
    return { ...DEFAULT_USER_CASE };
  }
  const params = new URLSearchParams(window.location.search);
  if (params.get("resetCase") === "1") {
    resetStoredUserCase();
    return { ...DEFAULT_USER_CASE };
  }
  const storedVersion = window.localStorage.getItem(USER_CASE_SCHEMA_VERSION_KEY);
  if (storedVersion !== String(CASE_SCHEMA_VERSION)) {
    resetStoredUserCase();
    return { ...DEFAULT_USER_CASE };
  }
  const raw = window.localStorage.getItem(USER_CASE_STORAGE_KEY);
  if (!raw) {
    persistUserCase(DEFAULT_USER_CASE);
    return { ...DEFAULT_USER_CASE };
  }
  try {
    return sanitizeUserCase(JSON.parse(raw));
  } catch {
    resetStoredUserCase();
    return { ...DEFAULT_USER_CASE };
  }
}

export function persistUserCase(userCase: UserCase): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(USER_CASE_SCHEMA_VERSION_KEY, String(CASE_SCHEMA_VERSION));
  window.localStorage.setItem(USER_CASE_STORAGE_KEY, JSON.stringify(sanitizeUserCase(userCase)));
}

export function resetStoredUserCase(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(USER_CASE_STORAGE_KEY);
  window.localStorage.setItem(USER_CASE_SCHEMA_VERSION_KEY, String(CASE_SCHEMA_VERSION));
}

export function sanitizeUserCase(input: unknown): UserCase {
  const value = isRecord(input) ? input : {};
  const sanitized = {} as UserCase;
  for (const field of VISIBLE_CASE_FIELDS) {
    sanitized[field] = numberOrDefault(value[field], DEFAULT_USER_CASE[field]);
  }
  return sanitized;
}

export function normalizeUserCase(value: unknown): UserCase {
  return sanitizeUserCase(value);
}

function numberOrDefault(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
