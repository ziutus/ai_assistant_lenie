"""Internal NER microservice: wraps spaCy pl_core_news_lg behind a minimal HTTP API.

Not reachable from outside the lenie-net Docker network (no published port) —
see README.md. No auth: network isolation is the only access control.
"""

import spacy
from flask import Flask, jsonify, request

app = Flask(__name__)

_nlp = None


def get_nlp():
    """Lazily load the spaCy model on first use — keeps /healthz fast even before it's loaded."""
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("pl_core_news_lg")
    return _nlp


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.post("/ner")
def ner():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "'text' is required"}), 400

    doc = get_nlp()(text)
    entities = [
        # lemma: base form for grouping inflected Polish variants ("Tuska" -> "Tusk")
        {"text": ent.text, "label": ent.label_, "lemma": ent.lemma_, "start": ent.start_char, "end": ent.end_char}
        for ent in doc.ents
    ]
    return jsonify({"entities": entities})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090)
