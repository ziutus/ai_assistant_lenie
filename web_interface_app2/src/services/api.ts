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
  // Validate API key using /website_list — works in both AWS and Docker/NAS environments.
  // /infra/database/status only exists in AWS (API Gateway + Lambda).
  await client.get('/website_list', { params: { type: 'link', limit: 1 } });
}
