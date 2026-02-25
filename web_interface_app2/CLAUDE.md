# web_interface_app2

Admin panel for Lenie AI, deployed at `app2.dev.lenie-ai.eu`.

## Tech Stack

- Vite 6 + React 18 + TypeScript
- React Bootstrap 2 + Bootstrap 5
- React Router v6, axios

## Development

```bash
npm install
npm run dev      # Dev server on port 3001
npm run build    # Production build → build/
npm run lint     # TypeScript check
```

## Authentication

Uses the existing backend API key as password — no backend changes needed.

- Login form sends `GET /website_list?type=link&limit=1` with `x-api-key` header
- Success → credentials saved to localStorage (prefix `lenie_app2_`), redirect to dashboard
- Failure → "Invalid credentials" error message

## Deployment

Deploy to S3 + CloudFront (`app2.dev.lenie-ai.eu`). The script resolves S3 bucket and CloudFront distribution ID from SSM Parameter Store.

```bash
./deploy.sh                      # Full build + deploy to S3 + CF invalidation
./deploy.sh --skip-build         # Deploy existing build/ only
./deploy.sh --skip-invalidation  # Skip CF cache invalidation
```

SSM parameters used:
- `/${PROJECT_CODE}/${ENVIRONMENT}/s3/app2-web/name` — S3 bucket name
- `/${PROJECT_CODE}/${ENVIRONMENT}/cloudfront/app2/id` — CloudFront distribution ID

Environment variables: `PROJECT_CODE` (default: `lenie`), `ENVIRONMENT` (default: `dev`), `AWS_REGION` (default: `us-east-1`).

## Project Structure

```
src/
├── main.tsx                  # Entry: AuthProvider + BrowserRouter + Bootstrap CSS
├── App.tsx                   # Routes: /login (public), /* (RequireAuth)
├── vite-env.d.ts
├── types/index.ts            # AuthState, AuthContextType
├── context/AuthContext.tsx    # Provider with login()/logout(), localStorage persistence
├── services/
│   ├── storage.ts            # localStorage helpers (prefix lenie_app2_)
│   └── api.ts                # axios helper + API key validation
├── components/RequireAuth.tsx # Route guard → redirect to /login
├── pages/
│   ├── LoginPage.tsx         # Login form (Bootstrap Card, centered)
│   └── DashboardPage.tsx     # Placeholder: "Welcome" + logout
└── styles/index.css          # Minimal custom styles
```
