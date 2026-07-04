import type { ApiType } from "../../../types";
import { DEFAULT_API_URLS } from "../../../types";

const KEYS = {
  apiType: "lenie_apiType",
  apiUrl: "lenie_apiUrl",
  apiKey: "lenie_apiKey",
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
