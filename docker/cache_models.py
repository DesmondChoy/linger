"""Fetch public local inference weights during image build, never on startup."""

import hashlib
import json
import os
from pathlib import Path

from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

from apps.backend.hybrid_librarian import EMBEDDING_MODEL, RERANKER_MODEL

cache = Path(os.environ["FASTEMBED_CACHE_PATH"])
embedding = TextEmbedding(model_name=EMBEDDING_MODEL)
reranker = TextCrossEncoder(model_name=RERANKER_MODEL)
list(embedding.query_embed("A reader opens a book."))
list(reranker.rerank("book", ["A reader opens a book."]))
files = {}
for path in sorted(cache.rglob("*")):
    if path.is_file() and ".locks" not in path.parts and path.name != "manifest.json":
        with path.open("rb") as stream:
            files[str(path.relative_to(cache))] = hashlib.file_digest(stream, "sha256").hexdigest()
(cache / "manifest.json").write_text(json.dumps({
    "models": [EMBEDDING_MODEL, RERANKER_MODEL], "files": files,
}, indent=2) + "\n")
