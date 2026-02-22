# Frontend (React)

React 18 single-page application for managing documents and running AI operations (translation, text correction, embedding, similarity search). Built with Create React App.

See [CLAUDE.md](CLAUDE.md) for detailed documentation (directory structure, pages & routes, architecture, API communication, dependencies). For the full project architecture see the [root CLAUDE.md](../CLAUDE.md).

## Running

```bash
npm start         # Dev server (port 3000)
npm run build     # Production build
npm test          # Run tests
```

## Docker

```bash
docker run --rm -p 3000:3000 --name lenie-ai-frontend -d lenie-ai-frontend:latest
```
