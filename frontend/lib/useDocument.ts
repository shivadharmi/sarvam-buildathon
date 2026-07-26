"use client";

/**
 * One document, addressed by the URL.
 *
 * The document is the only thing a reader page carries across a reload: it is
 * identified by the address, not held in a session. Everything said about it
 * lives in useConversation and does not survive.
 */

import { useCallback, useEffect, useState } from "react";

import { ApiError, getDocument } from "./api";
import type { DigitisedDoc } from "./types";

/**
 * Mirrors the backend's own doc_id allowlist (`cache._path_for`). Checked here
 * so a hand-edited address is answered honestly instead of being sent to the
 * server as a path to resolve.
 */
const SAFE_DOC_ID = /^[a-z0-9_]+$/;

/**
 * "missing" and "unreachable" are kept apart on purpose. Telling a reader we
 * do not have their document when we simply could not ask is the same
 * dishonesty as answering "not stated" for a question we never checked.
 */
export type DocumentState = "loading" | "ready" | "missing" | "unreachable";

export interface DocumentHandle {
  doc: DigitisedDoc | null;
  state: DocumentState;
  /** The server's own words, when we could not reach it. */
  error: string | null;
  /** Re-fetch after the page has been read again in another language. */
  reload: () => void;
}

export function useDocument(docId: string): DocumentHandle {
  const [doc, setDoc] = useState<DigitisedDoc | null>(null);
  const [state, setState] = useState<DocumentState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!docId || !SAFE_DOC_ID.test(docId)) {
      setDoc(null);
      setState("missing");
      return;
    }

    let cancelled = false;
    setState("loading");
    setError(null);

    getDocument(docId)
      .then((loaded) => {
        if (cancelled) return;
        setDoc(loaded);
        setState("ready");
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setDoc(null);
        // 404 is the only status that means we do not have it. Anything else
        // is us failing to look, and says so.
        if (cause instanceof ApiError && cause.status === 404) {
          setState("missing");
        } else {
          setState("unreachable");
          setError(
            cause instanceof ApiError
              ? cause.message
              : "That document could not be loaded.",
          );
        }
      });

    return () => {
      cancelled = true;
    };
  }, [docId, nonce]);

  const reload = useCallback(() => setNonce((current) => current + 1), []);

  return { doc, state, error, reload };
}
