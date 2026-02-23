import type { AuthState } from '../types';

const PREFIX = 'lenie_app2_';

const KEYS = {
  username: `${PREFIX}username`,
  apiKey: `${PREFIX}apiKey`,
  apiUrl: `${PREFIX}apiUrl`,
} as const;

export const DEFAULT_API_URL = 'https://api.dev.lenie-ai.eu';

export function loadAuth(): AuthState | null {
  const apiKey = localStorage.getItem(KEYS.apiKey);
  if (!apiKey) return null;

  return {
    username: localStorage.getItem(KEYS.username) || '',
    apiKey,
    apiUrl: localStorage.getItem(KEYS.apiUrl) || DEFAULT_API_URL,
  };
}

export function saveAuth(state: AuthState): void {
  localStorage.setItem(KEYS.username, state.username);
  localStorage.setItem(KEYS.apiKey, state.apiKey);
  localStorage.setItem(KEYS.apiUrl, state.apiUrl);
}

export function clearAuth(): void {
  localStorage.removeItem(KEYS.username);
  localStorage.removeItem(KEYS.apiKey);
  localStorage.removeItem(KEYS.apiUrl);
}
