"""HTTP API for the frontend. One verb per endpoint, no session state.

The contract is deliberately small: list documents, fetch one, ask a question.
Anything the UI needs to render a citation is already on the AnswerRecord.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import cache
from .cli import DOCUMENTS
from .models import AnswerRecord, AskRequest, DigitisedDoc, NoteAcknowledgement
from .pipeline import handle
from .sarvam_http import AuthError, ChatError, RateLimitError

app = FastAPI(title="Ask the Document", version="0.1.0")

# The frontend is served separately in dev; lock this down before any real
# deployment beyond the demo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _require(doc_id: str) -> DigitisedDoc:
    doc = cache.load(doc_id) if doc_id in DOCUMENTS else None
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"{doc_id} is not digitised yet. Run: askdoc.cli digitise --doc {doc_id}",
        )
    return doc


@app.get("/documents", response_model=list[DigitisedDoc])
def list_documents() -> list[DigitisedDoc]:
    """Every document that has been digitised and cached."""
    return [doc for doc_id in DOCUMENTS if (doc := cache.load(doc_id))]


@app.get("/documents/{doc_id}", response_model=DigitisedDoc)
def get_document(doc_id: str) -> DigitisedDoc:
    return _require(doc_id)


@app.post("/ask", response_model=AnswerRecord | NoteAcknowledgement)
def ask_question(request: AskRequest) -> AnswerRecord | NoteAcknowledgement:
    """Answer a question about one document, or honestly decline.

    A failure to reach the model is reported as an error, never as
    "not stated" -- conflating "we could not check" with "the document does
    not say" would be exactly the dishonesty this product exists to prevent.
    """
    doc = _require(request.doc_id)

    try:
        return handle(
            doc,
            request.question,
            history=request.history,
            corrections=request.corrections,
        )
    except AuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ChatError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach the model, so this question was not checked. {exc}",
        ) from exc


@app.get("/health")
def health() -> dict[str, object]:
    return {"ok": True, "documents": [d.doc_id for d in list_documents()]}
