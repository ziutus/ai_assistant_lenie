# Project Lenie: Personal AI Assistant

Project Lenie is named after Lenie Clarke — the protagonist of Peter Watts' novel "Starfish,"
who ultimately becomes an agent of extinction for the world as we know it. The name is
a deliberate nod: I'm not convinced that AI won't end up doing the same to our civilization.
That said, Lenie offers advanced solutions for collecting, managing, and searching data
using Large Language Models (LLMs).

Lenie enables users to:
* collect and manage links, allowing easy searching of accumulated references using LLM,
* download content from webpages and store it in a PostgreSQL database for later search in a private archive,
* transcribe YouTube videos and store them in a database, facilitating the search for interesting segments (given the ease of finding engaging videos compared to books or articles).

Lenie's functionalities represent an advanced integration of AI technology with users' daily needs, providing efficient data management and deeper content analysis and utilization. However, similar to the literary character who brings inevitable consequences of her existence, Lenie raises questions about the boundaries of technology and our own control over it. It is both a fascinating and daunting tool that requires a conscious approach and responsible usage to maximize benefits and minimize risks associated with the increasing role of artificial intelligence in our lives.

This is a side project. Please be aware that the code is under active refactoring and correction as I'm still learning Python and LLMs.

## Target Vision

Lenie is evolving into something bigger: a **private knowledge base in an Obsidian vault, managed by Claude Desktop, powered by Lenie-AI as an MCP (Model Context Protocol) server** for searching and managing content.

Instead of interacting with Lenie through a web interface, the target workflow looks like this:
1. **Claude Desktop** acts as the primary interface — you ask questions, request summaries, or search your knowledge base through natural conversation
2. **Lenie-AI as MCP server** exposes its search, retrieval, and content management capabilities as MCP tools that Claude Desktop can call directly
3. **Obsidian vault** serves as the persistent, human-readable knowledge store — notes, articles, transcriptions, and AI-generated summaries all live as markdown files you own and control

This means transitioning from the current architecture (Flask REST API + React SPA accessed through a browser) to an MCP server model where the AI assistant itself becomes the interface. The Flask backend's endpoints (semantic search, content download, text processing) become MCP tools. The React frontend becomes optional — useful for bulk operations and browsing, but no longer the primary way to interact with your knowledge.

The Chrome/Kiwi browser extension remains essential for capturing content from the web.

## Roadmap

### Phase 1: Current State

See [Current Architecture](#current-architecture) for a detailed breakdown of what exists today — Flask REST API backend, React SPA frontend, PostgreSQL with pgvector, AWS serverless deployment, and Chrome/Kiwi browser extension.

### Phase 2: MCP Server Foundation

- Implement MCP server protocol — expose search, retrieve, and content management endpoints as MCP tools
- Claude Desktop integration — configure Lenie-AI as an MCP server in Claude Desktop
- API adaptation — adjust endpoint patterns for MCP tool consumption while maintaining backward compatibility with the existing REST API
- Remove legacy Add URL app (`web_add_url_react`) and its dedicated API Gateway — fully replaced by the Chrome/Kiwi browser extension

### Phase 3: Obsidian Integration

- Obsidian vault synchronization — link database content with markdown files in a local vault
- Semantic search from within Obsidian via Claude Desktop + MCP — ask questions about your knowledge base without leaving your notes
- Advanced vector search refinements for personal knowledge management workflows

### Phase 4: Scaling & Deployment Options

- ECS deployment — containerized scaling with managed orchestration
- EKS deployment — Kubernetes-based scaling for complex workloads
- Multi-environment support — parameterized deployments across dev/qa/prod

### Phase 5: LLM Text Analysis

- Automatic document analysis via LLM — extract structured metadata as JSON (author, topic, countries, data source, people, organizations)
- JSONB storage in PostgreSQL with GIN indexes for metadata search
- Frontend UI for viewing, editing, and filtering by analysis results
- Batch processing for existing documents without analysis

### Phase 6: Multiuser Support

- User authentication via AWS Cognito (registration, login, JWT tokens)
- Data ownership — `user_id` column in database tables, per-user data isolation
- Replace shared `x-api-key` with per-user Cognito auth tokens across all clients
- Login/logout UI in frontend applications (React SPA, Chrome extension, Add URL app)
- User management admin panel (user list, blocking, per-user statistics)

## Current Architecture

- **Backend** — Flask REST API (Python 3.11) serving 18 endpoints with `x-api-key` auth. Handles document CRUD, text processing, AI embeddings, and vector similarity search
- **Web Interface** — React 18 SPA for browsing, editing, and AI-processing documents. Supports two backend modes: AWS Serverless (Lambda) and Docker (Flask)
- **Browser Extension** — Chrome/Kiwi Manifest v3 extension for capturing webpages and sending them to the backend
- **Database** — PostgreSQL 17 with pgvector for vector similarity search (1536-dim embeddings)
- **AWS Serverless** — API Gateway, Lambda functions, SQS queues, Step Functions for cost-optimized processing
- **AI Services** — OpenAI, AWS Bedrock, Google Vertex AI, CloudFerro Bielik
- **Docker** — docker compose stack with Flask + PostgreSQL + React for local development
- **Kubernetes** — Kustomize-based deployment with GKE dev overlay (experimental)

See [CLAUDE.md](CLAUDE.md) for the full architecture reference.

## Supported Platforms

| Platform | Support |
|---|---|
| Windows | Chrome + extension |
| Android | Kiwi Browser + extension |
| MacOS | None |

## Differences Compared to Corporate Knowledge Bases
In corporate knowledge bases, we don't assume that we have misleading, inappropriate, or propaganda-driven articles.
Every article is considered equally valid.

When dealing with sensitive, political, or money-related topics, we may encounter:
* state propaganda (especially on geopolitical and political topics)
* party-driven thematic propaganda (anti-EU, refugees and immigrants, vaccines, etc.)
* corporate Public Relations campaigns (e.g., "it's not true that Tesla fell behind in autonomous and electric vehicle development")
* online scammers
* amateur texts posing as expert content (e.g., tutorials advising to disable all Linux security mechanisms because they're "inconvenient")
* internet trolls
* mass AI-generated content with no real value, created to gain Google search rankings

Therefore, there is a need to build a mechanism for assessing the credibility of sources (e.g., websites or YouTube videos) and authors.

It is also necessary to provide the ability to select only specific sources (from all available ones) and to explicitly cite data sources in responses.

## Challenges to Solve When Building Such a Solution

When working with corporate documents, the most common challenge is converting corporate wikis, Notion pages, or Word documents into a format suitable for LLMs.

When working with internet sources, the challenges are different:
* content is behind a paywall (the solution I use is a browser extension),
* difficulty importing data from platforms like LinkedIn, Facebook, etc. (they protect against easy content scraping),
* need to write content analyzers for pages captured by the extension to reduce costs (see below),
* quality of subtitles generated by YouTube's automatic translation,
* cost (and quality) of audio-to-text conversion

Example document sizes:
* Original HTML document, a saved copy of an article from Onet.pl: 300 KB,
* Converted to markdown format: 15 KB,
* Article text only: 3000 words,

Large language models, such as those from OpenAI, handle the analysis of an entire article page in markdown format very well, but this generates significant costs compared to analyzing just the article text.

Data sources for a personal assistant:
* SMS messages, i.e., messages up to 120 characters (Google Play has been blocking apps with SMS access for some time; you need to install a "custom" app, e.g., Make),
* emails (HTML format), several hundred words,
* PDF documents (e.g., invoices) and DOC files (e.g., job requirements),
* ebooks (hundreds of thousands of words, need to be split into chunks before embedding),
* images (e.g., photos of book pages, invoices, photos with significant content),
* WhatsApp chats, Messenger, etc.,
* calendar access,
* browsing history (access to SQLite, e.g., in Chrome),
* access to the paid Meetup API (GraphQL) to know who you might meet and who to be cautious of,
* access to paid APIs for querying the Polish National Court Register (KRS) (to know if a contact has their own company, foundation, etc.)


## Scalability and Reliability
For a single user, a PostgreSQL database with appropriate extensions is sufficient.

If we want a single user to be able to work from different devices, we need to enable
them to work with an external server running 24/7.
In that case, we must ensure:
* availability of the solution from anywhere in the world,
* security of the solution (need for security updates, DDoS protection, etc.),
* low costs,
* minimal maintenance time required.



For a larger number of users, we need to consider:
* infrastructure scaling costs (e.g., database),
* solution performance (we can add containers or go with serverless solutions and queues),
* security of data isolation for each client.

## Used Technologies
In this project, I'm using:
* Python as the server backend
* PostgreSQL as the embedding database
* React as the web interface (under development)
* HashiCorp Vault for secrets (for local and Kubernetes environments)
* AWS as the deployment platform (as I'm lazy and don't want to manage infrastructure)

Current deployment methods:
* Docker Compose (local development)
* AWS Lambda (production, event-driven serverless)
* Kubernetes with Kustomize (experimental)

See [Roadmap](#roadmap) for planned deployment options (ECS, EKS).

## Services That Can Be Used to Get Data

| Service name | Provider   | Description | Link |
|-------------|------------|---|------|
| Textract    | AWS        | PDF to text | https://aws.amazon.com/textract/     |
| AssemblyAI  | AssemblyAI | Speech to text ($0.12 per hour) | https://www.assemblyai.com/ |

## Documentation

| Document | Description |
|----------|-------------|
| [CLAUDE.md](CLAUDE.md) | Full architecture reference |
| [docs/Python_Dependencies.md](docs/Python_Dependencies.md) | Dependency management with uv |
| [docs/Docker_Local.md](docs/Docker_Local.md) | Docker development and deployment |
| [docs/VM_Setup.md](docs/VM_Setup.md) | Virtual machine setup |
| [docs/AWS_Infrastructure.md](docs/AWS_Infrastructure.md) | AWS infrastructure |
| [docs/Code_Quality.md](docs/Code_Quality.md) | Linting and security scanning |
| [docs/API_Usage.md](docs/API_Usage.md) | API request examples |
| [docs/CI_CD.md](docs/CI_CD.md) | CI/CD pipelines |

## Why Do We Need Our Own LLM?
So far, available LLMs operate in English or implicitly translate to English, losing context or meaning.

Let's translate two texts into English:

Sasiad wyszedl z psem o 6 rano.
(The neighbor went out with a dog at 6 AM.)

And:

Psy przyszly po sasiada o 6 rano.
(The "dogs" came for the neighbor at 6 AM.)

As Poles, we perfectly understand the difference between an animal and the slang term for police officers ("psy" literally means "dogs" but is slang for "cops"), but you need to know the cultural context.

Now we have Bielik (https://bielik.ai), which perfectly understands the magic of this sentence:

![img.png](bielik_psy_pl.png)

You can use Bielik on [CloudFerro.com](https://sherlock.cloudferro.com/#pricing)
