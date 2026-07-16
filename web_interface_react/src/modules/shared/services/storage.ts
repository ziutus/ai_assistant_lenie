import type { ApiType } from "../../../types";
import { DEFAULT_API_URLS } from "../../../types";

const KEYS = {
  apiType: "lenie_apiType",
  apiUrl: "lenie_apiUrl",
  apiKey: "lenie_apiKey",
  obsidianVaultName: "lenie_obsidianVaultName",
  listFilters: "lenie_listFilters",
} as const;

export function loadConnectionConfig(): {
  apiType: ApiType;
  apiUrl: string;
  apiKey: string | undefined;
} {
  // "Docker" is the only backend mode since the AWS API decommission —
  // ignore any stale "AWS Serverless" value left in localStorage
  const apiType: ApiType = "Docker";
  const storedKey = localStorage.getItem(KEYS.apiKey);
  return {
    apiType,
    apiUrl: localStorage.getItem(KEYS.apiUrl) || DEFAULT_API_URLS[apiType],
    apiKey: storedKey ? atob(storedKey) : undefined,
  };
}

export function saveConnectionConfig(config: {
  apiType: ApiType;
  apiUrl: string;
  apiKey: string;
}): void {
  localStorage.setItem(KEYS.apiType, config.apiType);
  localStorage.setItem(KEYS.apiUrl, config.apiUrl);
  localStorage.setItem(KEYS.apiKey, btoa(config.apiKey));
}

export function clearConnectionConfig(): void {
  localStorage.removeItem(KEYS.apiType);
  localStorage.removeItem(KEYS.apiUrl);
  localStorage.removeItem(KEYS.apiKey);
}

export function isConnected(): boolean {
  return !!localStorage.getItem(KEYS.apiKey);
}

// Document-list filters survive a page reload (stored per browser). Saved as a
// partial merge so the context (type/state/search) and the list page
// (obsidian filter) can persist their fields independently.
export interface ListFilters {
  documentType: string;
  documentState: string;
  searchText: string;
  searchType: string;
  obsidianFilter: "none" | "missing" | "has";
}

const DEFAULT_LIST_FILTERS: ListFilters = {
  documentType: "link",
  documentState: "NEED_MANUAL_REVIEW",
  searchText: "",
  searchType: "strict",
  obsidianFilter: "none",
};

export function loadListFilters(): ListFilters {
  try {
    const raw = localStorage.getItem(KEYS.listFilters);
    if (!raw) return { ...DEFAULT_LIST_FILTERS };
    return { ...DEFAULT_LIST_FILTERS, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_LIST_FILTERS };
  }
}

export function saveListFilters(filters: Partial<ListFilters>): void {
  localStorage.setItem(KEYS.listFilters, JSON.stringify({ ...loadListFilters(), ...filters }));
}

// The Obsidian vault name is device-specific (e.g. Obsidian Sync uses a
// different display name per device for the same synced vault), so it's
// stored locally per browser/device rather than coming from the backend.
export function loadObsidianVaultName(): string {
  return localStorage.getItem(KEYS.obsidianVaultName) || "";
}

export function saveObsidianVaultName(vaultName: string): void {
  if (vaultName.trim()) {
    localStorage.setItem(KEYS.obsidianVaultName, vaultName.trim());
  } else {
    localStorage.removeItem(KEYS.obsidianVaultName);
  }
}
