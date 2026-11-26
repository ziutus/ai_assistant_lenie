"""Compare relation extraction models; GET-only source access, external result files."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from library.relation_extraction import SYMMETRIC, extract_relations, normalized


def same_word(a, b):
    """One word in two Polish grammatical forms: a long common stem and a short ending on both sides."""
    if a == b:
        return True
    common = len(os.path.commonprefix([a, b]))
    shortest = min(len(a), len(b))
    if shortest <= 4:  # short names ("ada" / "ady") allow only the last letter to change
        return common >= shortest - 1 >= 2 and abs(len(a) - len(b)) <= 1
    return common >= shortest - 2 and len(a) - common <= 3 and len(b) - common <= 3


def same_name(a, b):
    """Equal names up to inflection; the number of words must match, so "Jan Kowal" is not "Kowal"."""
    left, right = a.split(), b.split()
    return len(left) == len(right) and all(same_word(x, y) for x, y in zip(left, right))


def score_relations(proposals, gold):
    aliases = {}
    for canonical, variants in gold.get("aliases", {}).items():
        for variant in [canonical, *variants]:
            aliases.setdefault(normalized(variant), set()).add(normalized(canonical))

    def name(value):
        key = normalized(value)
        matches = aliases.get(key, set())
        if not matches:
            matches = {c for variant, targets in aliases.items() if same_name(key, variant) for c in targets}
        return next(iter(matches)) if len(matches) == 1 else key

    def pair(a, b, c, d):
        return same_name(a, c) and same_name(b, d)

    def matches(p, g, reverse=False):
        roles = g.get("relations", [g.get("relation")])
        if p["relation"] not in roles:
            return False
        a, b = name(p["subject"]), name(p["object"])
        c, d = name(g["subject"]), name(g["object"])
        symmetric = p["relation"] in SYMMETRIC or g.get("symmetric") is True
        if reverse:
            return not symmetric and pair(a, b, d, c)
        return pair(a, b, c, d) or (symmetric and pair(a, b, d, c))

    required = [r for r in gold.get("relations", []) if r.get("required", True)]
    optional = [r for r in gold.get("relations", []) if not r.get("required", True)]
    matched, unmatched, forbidden, wrong_direction = set(), [], [], []
    correct = ignored = claim_correct = 0
    for p in proposals:
        if any(matches(p, g) for g in gold.get("forbidden", [])):
            forbidden.append(p)
            continue
        possible = [i for i, g in enumerate(required) if matches(p, g)]
        available = [i for i in possible if i not in matched]
        if available:
            i = next((i for i in available if required[i].get("claim") == p.get("claim")), available[0])
            matched.add(i)
            correct += 1
            claim_correct += int(p.get("claim") == required[i].get("claim"))
        elif any(matches(p, g) for g in optional):
            ignored += 1
        elif any(matches(p, g, reverse=True) for g in required + optional):
            wrong_direction.append(p)
        else:
            unmatched.append(p)
    denominator = len(proposals) - ignored
    precision = correct / denominator if denominator else None
    recall = len(matched) / len(required) if required else None
    f1 = (2 * precision * recall / (precision + recall) if precision and recall else
          0.0 if precision is not None and recall is not None else None)
    return {"found": len(proposals), "correct": correct, "precision": precision, "recall": recall, "f1": f1,
            "wrong_direction_count": len(wrong_direction), "forbidden_hits": len(forbidden),
            "claim_type_accuracy": claim_correct / correct if correct else None,
            "unmatched_count": len(unmatched), "unmatched": unmatched, "forbidden": forbidden,
            "wrong_direction": wrong_direction, "optional_matches": ignored,
            "missed": [g for i, g in enumerate(required) if i not in matched]}


def validate_output_path(value):
    """Reject this checkout, parent checkout, other git repos and resolved junction targets."""
    path = Path(value).expanduser().resolve()
    source = Path(__file__).resolve()
    roots = [p for p in source.parents if (p / ".git").exists()]
    if any(path == root or root in path.parents for root in roots):
        raise ValueError("Output must be outside the git repository")
    if any((p / ".git").exists() for p in [path, *path.parents]):
        raise ValueError("Output must be outside any git repository")
    return path


def flatten_entities(entities):
    if isinstance(entities, dict):
        return [dict(row, entity_type=kind) for kind, rows in entities.items()
                if kind in ("persName", "orgName") for row in rows]
    return entities


def read_documents(ids, input_dir, *, get=None):
    if input_dir:
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(input_dir).glob("*.json"))]
    if get is None:
        import requests
        get = requests.get
    base, key = os.environ["LENIE_API_URL"].rstrip("/"), os.environ["LENIE_API_KEY"]
    documents = []
    for doc_id in ids:
        responses = []
        for endpoint in ("website_get", "website_entities"):
            response = get(f"{base}/{endpoint}", params={"id": doc_id}, headers={"x-api-key": key}, timeout=60)
            response.raise_for_status()
            responses.append(response.json())
        doc, entities = responses
        documents.append({"id": doc_id, "text": doc.get("text") or doc.get("text_md") or "",
                          "entities": entities["entities"]})
    return documents


def model_capabilities(model):
    from library.ai import GOOGLE_MODELS, SHERLOCK_MODELS, SHERLOCK_VISION_MODELS, _registry_provider
    from library.entity_description_batch import supports_structured_output

    system = (model.startswith(("arklabs/", "openrouter/"))
              or model in GOOGLE_MODELS + SHERLOCK_MODELS + SHERLOCK_VISION_MODELS
              or _registry_provider(model) in ("cloudferro", "arklabs", "openrouter", "google-vertexai"))
    return {"system_supported": system, "structured_output": supports_structured_output(model)}


def positive(value):
    value = int(value)
    if value < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return value


SUMMARY_HEADER = [
    "| Document | Run | Found | Correct | Precision | Recall | F1 | Wrong direction | Forbidden | Claim accuracy | "
    "Unmatched | Rejected | Calls | Tokens | Cost | Seconds |",
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]


def summary_row(result):
    metrics, r = result["metrics"], result["report"]
    cells = [result["document_id"], result["run"], *[metrics.get(k) for k in (
        "found", "correct", "precision", "recall", "f1", "wrong_direction_count", "forbidden_hits",
        "claim_type_accuracy", "unmatched_count")], json.dumps(r["rejected"]), r["calls"],
        r["llm_tokens"], f"{r['llm_cost_amount']} {r['llm_cost_currency']}", round(r["elapsed_seconds"], 3)]
    return "| " + " | ".join("unknown" if c is None else str(c) for c in cells) + " |"


def write_summary(out, model, results):
    model_key = hashlib.sha256(model.encode()).hexdigest()[:16]
    lines = [f"# Model: {model}", "", *SUMMARY_HEADER, *[summary_row(r) for r in results]]
    (out / f"{model_key}-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def rescore(out, gold_dir):
    """Score the saved result files again (after a gold or matching change); no model is called."""
    by_model = {}
    for path in sorted(out.glob("*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        gold_path = gold_dir / f"{int(result['document_id'])}.json"
        if gold_path.exists():
            result["metrics"] = score_relations(result["relations"], json.loads(gold_path.read_text(encoding="utf-8")))
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        by_model.setdefault(result["model"], []).append(result)
    for model, results in by_model.items():
        write_summary(out, model, results)
    return len(by_model)


def main(argv=None, *, ask=None, capabilities=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--rescore", action="store_true", help="Score the results in --out again; needs --gold")
    source.add_argument("--documents", help="Comma-separated positive document IDs")
    source.add_argument("--input", type=Path)
    parser.add_argument("--models")
    parser.add_argument("--gold", type=Path)
    parser.add_argument("--out", required=True)
    parser.add_argument("--chunk-chars", type=positive, default=3500)
    parser.add_argument("--runs", type=positive, default=1)
    parser.add_argument("--no-verify", action="store_true")
    args = parser.parse_args(argv)
    try:
        out = validate_output_path(args.out)
        ids = [positive(v.strip()) for v in args.documents.split(",")] if args.documents else []
    except (ValueError, argparse.ArgumentTypeError) as exc:
        parser.error(str(exc))
    if args.rescore:
        if not args.gold:
            parser.error("--rescore needs --gold")
        return 0 if rescore(out, args.gold) else 1
    models = [m.strip() for m in (args.models or "").split(",") if m.strip()]
    if not models:
        parser.error("at least one model is required")
    documents = read_documents(ids, args.input)
    # Validate all inputs before spending money or writing outputs. Numeric IDs also make filenames safe.
    for doc in documents:
        doc["id"] = positive(str(doc["id"]))
        if not isinstance(doc.get("text"), str):
            parser.error("document text must be a string")
        doc["entities"] = flatten_entities(doc.get("entities", []))
    if not documents:
        parser.error("no input documents")
    if ask is None:
        from library.ai import ai_ask
        ask = ai_ask
    capabilities = capabilities or model_capabilities
    out.mkdir(parents=True, exist_ok=True)
    for model in models:
        model_key = hashlib.sha256(model.encode()).hexdigest()[:16]
        options = capabilities(model)
        results = []
        for doc in documents:
            gold_path = args.gold / f"{doc['id']}.json" if args.gold else None
            gold = json.loads(gold_path.read_text(encoding="utf-8")) if gold_path and gold_path.exists() else None
            for run in range(1, args.runs + 1):
                result = extract_relations(doc["text"], doc["entities"], model, ask=ask, document_id=doc["id"],
                                           chunk_chars=args.chunk_chars, verify=not args.no_verify, **options)
                metrics = score_relations(result["relations"], gold) if gold is not None else {"found": len(result["relations"])}
                result.update(document_id=doc["id"], model=model, run=run, metrics=metrics)
                (out / f"{doc['id']}-{model_key}-{run}.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                results.append(result)
        write_summary(out, model, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
