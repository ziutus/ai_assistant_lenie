// "AWS Serverless" removed 2026-07-04 — the document-serving Lambdas
// (app-server-db/app-server-internet) were decommissioned 2026-07-02 and no
// frontend can browse documents through the AWS API anymore.
// Restoration notes: docs/aws-serverless-restoration.md
export type ApiType = "Docker";

export const DEFAULT_API_URLS: Record<ApiType, string> = {
  Docker: "http://192.168.200.7:5055",
};
