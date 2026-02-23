import type { ApiType } from "../../../types";

const KEYS = {
  apiType: "lenie_apiType",
  apiUrl: "lenie_apiUrl",
  infraApiUrl: "lenie_infraApiUrl",
  apiKey: "lenie_apiKey",
} as const;

export const DEFAULT_URLS: Record<ApiType, { apiUrl: string; infraApiUrl: string }> = {
  "AWS Serverless": {
    apiUrl: "https://api.dev.lenie-ai.eu",
    infraApiUrl: "https://api.dev.lenie-ai.eu",
  },
  Docker: {
    apiUrl: "http://localhost:5000",
    infraApiUrl: "http://localhost:5000",
  },
};

export function loadConnectionConfig(): {
  apiType: ApiType;
  apiUrl: string;
  infraApiUrl: string;
  apiKey: string | undefined;
} {
  const apiType = (localStorage.getItem(KEYS.apiType) as ApiType) || "AWS Serverless";
  const defaults = DEFAULT_URLS[apiType];
  return {
    apiType,
    apiUrl: localStorage.getItem(KEYS.apiUrl) || defaults.apiUrl,
    infraApiUrl: localStorage.getItem(KEYS.infraApiUrl) || defaults.infraApiUrl,
    apiKey: localStorage.getItem(KEYS.apiKey) || undefined,
  };
}

export function saveConnectionConfig(config: {
  apiType: ApiType;
  apiUrl: string;
  infraApiUrl: string;
  apiKey: string;
}): void {
  localStorage.setItem(KEYS.apiType, config.apiType);
  localStorage.setItem(KEYS.apiUrl, config.apiUrl);
  localStorage.setItem(KEYS.infraApiUrl, config.infraApiUrl);
  localStorage.setItem(KEYS.apiKey, config.apiKey);
}

export function clearConnectionConfig(): void {
  localStorage.removeItem(KEYS.apiType);
  localStorage.removeItem(KEYS.apiUrl);
  localStorage.removeItem(KEYS.infraApiUrl);
  localStorage.removeItem(KEYS.apiKey);
}

export function isConnected(): boolean {
  return !!localStorage.getItem(KEYS.apiKey);
}
