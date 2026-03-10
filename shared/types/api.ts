export type ApiType = "AWS Serverless" | "Docker";

export const DEFAULT_API_URLS: Record<ApiType, string> = {
  "AWS Serverless": "https://api.dev.lenie-ai.eu",
  Docker: "http://192.168.200.7:5055",
};
