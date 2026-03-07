# Embeddings — Database Design

This document describes how vector embeddings are stored and queried in Project Lenie's PostgreSQL database.

## Overview

Embeddings are numerical vector representations of text, used for semantic similarity search. When a user searches for similar documents, the system converts the query text into a vector and finds documents whose vectors are closest (cosine similarity).

## Database Schema

Embeddings are stored in the `public.websites_embeddings` table:

| Column | Type | Description |
|--------|------|-------------|
| `id` | `serial PK` | Auto-incrementing primary key |
| `website_id` | `integer NOT NULL` | FK → `web_documents.id` (CASCADE delete) |
| `langauge` | `varchar(10)` | Language of the embedded text (note: legacy typo, kept for compatibility) |
| `text` | `text` | Text that was actually embedded (may be translated to English) |
| `text_original` | `text` | Original text before translation (if applicable) |
| `embedding` | `vector` | The vector embedding — dimensionless, supports any model |
| `model` | `varchar(100) NOT NULL` | Name of the embedding model used |
| `created_at` | `timestamp` | Row creation timestamp |

Schema file: [`backend/database/init/04-create-table.sql`](../backend/database/init/04-create-table.sql)

## Multi-Model Support

The `embedding` column uses pgvector's dimensionless `vector` type (no fixed dimension). This allows storing embeddings from different models with different vector sizes in the same table.

### Supported Models

| Model | Provider | Dimensions | Multilingual | Translation Required | Cost (per 1M tokens) | Documentation |
|-------|----------|-----------|--------------|---------------------|---------------------|---------------|
| `text-embedding-ada-002` | OpenAI | 1536 | Yes (but best with English) | **Yes** — translate to English first | $0.10 | [OpenAI Embeddings](https://platform.openai.com/docs/models/text-embedding-ada-002) |
| `amazon.titan-embed-text-v1` | AWS Bedrock | 1536 | Limited | No | $0.10 | [Titan Text Embeddings](https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html) |
| `amazon.titan-embed-text-v2:0` | AWS Bedrock | 1024 | Yes | No | $0.02 | [Titan Text Embeddings V2](https://aws.amazon.com/blogs/machine-learning/get-started-with-amazon-titan-text-embeddings-v2-a-new-state-of-the-art-embeddings-model-on-amazon-bedrock/) |
| `BAAI/bge-multilingual-gemma2` | CloudFerro (Sherlock) | 3584 | **Yes** (incl. Polish) | No | 0.52 PLN | [Model card (HuggingFace)](https://huggingface.co/BAAI/bge-multilingual-gemma2), [Sherlock pricing](https://sherlock.cloudferro.com/pl#pricing) |
| `intfloat/e5-mistral-7b-instruct` | CloudFerro (Sherlock) | 4096 | **Yes** (incl. Polish) | No | 0.52 PLN | [Model card (HuggingFace)](https://huggingface.co/intfloat/e5-mistral-7b-instruct), [Sherlock pricing](https://sherlock.cloudferro.com/pl#pricing) |
| `dunzhang/stella_en_1.5B_v5` | CloudFerro (Sherlock) | 1024 | No (English only) | **Yes** — translate to English first | 0.26 PLN | [Model card (HuggingFace)](https://huggingface.co/dunzhang/stella_en_1.5B_v5), [Sherlock pricing](https://sherlock.cloudferro.com/pl#pricing) |
| `BAAI/bge-m3` | ARK Labs | 1024 | **Yes** (100+ languages incl. Polish) | No | $0.01 | [Model card (HuggingFace)](https://huggingface.co/BAAI/bge-m3), [ARK Labs pricing](https://ark-labs.cloud/pricing/) |

The active model is configured via the `EMBEDDING_MODEL` environment variable.

### Language Handling

Some models work best (or only) with English text. The `embedding_need_translation()` function determines whether text must be translated to English before generating an embedding:

- **Translation required**: `text-embedding-ada-002` — Polish text should be translated to English first. The translated text is stored in `text`, and the original Polish text in `text_original`.
- **No translation needed**: All other models — they handle Polish text natively. The original text is stored directly in `text`.

This distinction is important because the project primarily collects Polish-language content.

## Indexing Strategy

Each embedding model produces vectors of a different dimension. pgvector indexes require a fixed dimension, so the database uses **HNSW partial indexes** — one per model:

```sql
CREATE INDEX idx_emb_ada002
  ON public.websites_embeddings USING hnsw ((embedding::vector(1536)) vector_cosine_ops)
  WHERE model = 'text-embedding-ada-002';

CREATE INDEX idx_emb_bge_m3
  ON public.websites_embeddings USING hnsw ((embedding::vector(1024)) vector_cosine_ops)
  WHERE model = 'BAAI/bge-m3';
```

**Why HNSW partial indexes?**

- **HNSW** (Hierarchical Navigable Small World) — faster than IVFFlat, works well with any dataset size, no need to pre-populate data before creating the index.
- **Partial indexes** (`WHERE model = '...'`) — each index covers only rows for one model. This is required because pgvector cannot build a single index over vectors of different dimensions.
- Similarity queries already filter by `model`, so PostgreSQL automatically uses the correct partial index.
- The dimensionless `vector` column requires an explicit cast (`embedding::vector(N)`) in the index definition.

**Limitation:** pgvector 0.8.1 HNSW supports max **2000 dimensions** for `vector_cosine_ops`. Models with larger vectors (`BAAI/bge-multilingual-gemma2`: 3584, `intfloat/e5-mistral-7b-instruct`: 4096) use sequential scan instead. This is acceptable for small-to-medium datasets.

### Adding a New Model

When adding support for a new embedding model:

1. Add the model to `embedding_models` set in [`backend/library/embedding.py`](../backend/library/embedding.py)
2. Add a new HNSW partial index in [`backend/database/init/04-create-table.sql`](../backend/database/init/04-create-table.sql):
   ```sql
   CREATE INDEX IF NOT EXISTS idx_emb_<short_name>
     ON public.websites_embeddings USING hnsw (embedding vector_cosine_ops)
     WHERE model = '<model-name>';
   ```
3. For existing databases, run the `CREATE INDEX` statement manually.

## Similarity Search

Similarity search uses **cosine distance** (`<=>` operator in pgvector). The query:

1. Converts user's search text into an embedding vector (using the same model as stored embeddings)
2. Finds rows in `websites_embeddings` where `model` matches
3. Ranks results by `1 - (embedding <=> query_vector)` (cosine similarity, 1.0 = identical)
4. Filters out results below a minimum similarity threshold (default: 0.30)
5. Joins with `web_documents` to return document metadata

**Important**: Search queries and stored embeddings must use the **same model**. Vectors from different models are not comparable.

## Model Comparison for Polish Language

Since the project primarily collects Polish-language content, choosing the right embedding model is critical. The table below summarizes quality and cost trade-offs for Polish text.

| Model | Polish Quality | Cost/1M tokens | Dimensions | Recommendation |
|-------|---------------|----------------|-----------|----------------|
| `BAAI/bge-multilingual-gemma2` | SOTA (best on [MTEB-pl](https://arxiv.org/abs/2405.10138), [MIRACL](https://huggingface.co/BAAI/bge-multilingual-gemma2)) | 0.52 PLN | 3584 | **Best quality** for Polish |
| `BAAI/bge-m3` | Very good (100+ languages) | $0.01 (~0.04 PLN) | 1024 | **Best price/quality ratio** |
| `intfloat/e5-mistral-7b-instruct` | Good | 0.52 PLN | 4096 | Same price as gemma2, lower Polish quality |
| `amazon.titan-embed-text-v2:0` | Limited | $0.02 | 1024 | OK if already using AWS |
| `dunzhang/stella_en_1.5B_v5` | Requires translation | 0.26 PLN | 1024 | English only — adds translation cost and latency |
| `amazon.titan-embed-text-v1` | Limited | $0.10 | 1536 | Legacy, not recommended |
| `text-embedding-ada-002` | Requires translation | $0.10 | 1536 | Legacy, expensive |

**Recommended models:**

- **Highest quality**: `BAAI/bge-multilingual-gemma2` — state-of-the-art on Polish benchmarks ([MTEB-pl](https://arxiv.org/abs/2405.10138)), native Polish support, no translation needed. Higher cost and larger vectors (3584 dim).
- **Best value**: `BAAI/bge-m3` — very good multilingual quality at ~13x lower cost than gemma2. Smaller vectors (1024 dim) mean less storage and faster search.

For more details on Polish embedding benchmarks, see [PL-MTEB: Polish Massive Text Embedding Benchmark](https://arxiv.org/abs/2405.10138) and [MMTEB: Massive Multilingual Text Embedding Benchmark](https://arxiv.org/abs/2502.13595).

## Relationship to Documents

- Each document (`web_documents`) can have **multiple embedding rows** — one per text chunk (for long documents split into parts) or one per model.
- Deleting a document (`web_documents`) automatically deletes all its embeddings via `ON DELETE CASCADE`.
- The `embedding_delete(model)` method removes all embeddings for a specific document and model before re-generating them (idempotent update).
