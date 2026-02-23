import axios from 'axios';

export function createApiClient(apiUrl: string, apiKey: string) {
  return axios.create({
    baseURL: apiUrl,
    headers: { 'x-api-key': apiKey },
    timeout: 10000,
  });
}

export async function validateApiKey(apiUrl: string, apiKey: string): Promise<void> {
  const client = createApiClient(apiUrl, apiKey);
  // Use /infra/database/status — responds regardless of DB state,
  // but still requires valid x-api-key (returns 403 on bad key).
  await client.get('/infra/database/status');
}
