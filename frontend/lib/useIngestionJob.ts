"use client";

/**
 * One upload, from the file the reader dropped to a document they can ask.
 *
 * Digitisation is slow, paid and multi-pass, so the reader is told which pass
 * is running rather than watching an unlabelled spinner: a page that takes
 * thirty seconds is tolerable if you can see it being read twice on purpose.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, getJob, setDocumentLanguage, uploadDocument } from "./api";
import { languageName } from "./languages";
import { isJobTerminal, jobOutcome } from "./types";
import type { JobStatus, UploadAccepted } from "./types";

const POLL_MS = 1000;

// Digitisation is slow, but not this slow. Without a ceiling a job the server
// forgot about polls forever behind a status line that never changes, which
// reads as "still working" when nothing is working.
const GIVE_UP_MS = 5 * 60 * 1000;

const GAVE_UP =
  "This is taking longer than it should. The page may still be processing — try again in a moment.";

export interface IngestionJob {
  /** The last status read from the server. Null when nothing is in flight. */
  job: JobStatus | null;
  /** Reader-facing sentence for the step running now, or null when idle. */
  message: string | null;
  /** True from handing over the file until a terminal state. */
  busy: boolean;
  /** The server's own words for a rejection or failure. Never paraphrased. */
  error: string | null;
  /** The detector declined to guess, and we are waiting on the picker. */
  needsLanguage: boolean;
  /**
   * The document a language choice applies to. Outlives one failed attempt on
   * purpose — losing the picker because the re-read call failed would leave
   * the reader holding a page they cannot open.
   */
  pendingDocId: string | null;
  upload: (file: File) => void;
  chooseLanguage: (docId: string, language: string) => void;
  reset: () => void;
}

/**
 * Reader-facing copy for a stage.
 *
 * "Re-reading in Telugu" names the language on purpose: it is the moment the
 * reader can catch a wrong guess, and they can only catch it if they are told.
 */
function stageMessage(job: JobStatus): string | null {
  switch (job.stage) {
    case "validating":
      return "Checking the file…";
    case "digitising_probe":
      return "Reading the page…";
    case "detecting":
      return "Working out the language…";
    case "digitising_final":
      return `Re-reading in ${languageName(job.detected_language)}…`;
    default:
      return null;
  }
}

/**
 * @param onReady Called once with the finished doc_id. The page reloads the
 *   document list and starts a fresh conversation on it — a re-digitised page
 *   has different line numbers, so earlier answers no longer point anywhere.
 */
export function useIngestionJob(onReady: (docId: string) => void): IngestionJob {
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Shown while the request is in flight, before there is a job to describe.
  const [sending, setSending] = useState<string | null>(null);
  const [pendingDocId, setPendingDocId] = useState<string | null>(null);

  // Held in a ref so a new callback identity on every page render does not
  // tear down and restart the poll.
  const ready = useRef(onReady);
  useEffect(() => {
    ready.current = onReady;
  }, [onReady]);

  const finish = useCallback((status: JobStatus) => {
    setJobId(null);
    setBusy(false);
    setSending(null);

    const outcome = jobOutcome(status);
    if (outcome === "ready") {
      if (status.doc_id) {
        setPendingDocId(null);
        ready.current(status.doc_id);
        setJob(null);
      } else {
        // Ready without an identity is not something to paper over: there is
        // no document to switch to, and pretending otherwise strands the reader.
        setError("The page was read, but the server did not say which document it is.");
      }
      return;
    }

    if (outcome === "failed") {
      setError(status.error ?? "That page could not be read.");
      return;
    }

    if (outcome === "needs_language" && status.doc_id) {
      setPendingDocId(status.doc_id);
    } else if (outcome === "needs_language") {
      setError(
        "The language could not be worked out, and there is no document to set it on. Try uploading the page again.",
      );
    }
  }, []);

  // Poll while a job is live. Clearing jobId — on a terminal state, a failure
  // or unmount — runs the cleanup and stops the interval.
  useEffect(() => {
    if (!jobId) return;

    let cancelled = false;
    const startedAt = Date.now();

    const tick = async () => {
      try {
        const next = await getJob(jobId);
        if (cancelled) return;

        setJob(next);
        if (isJobTerminal(next)) {
          finish(next);
        } else if (Date.now() - startedAt > GIVE_UP_MS) {
          setJobId(null);
          setBusy(false);
          setSending(null);
          setError(GAVE_UP);
        }
      } catch (cause: unknown) {
        if (cancelled) return;
        setJobId(null);
        setBusy(false);
        setSending(null);
        setError(
          cause instanceof ApiError
            ? cause.message
            : "Lost track of the page while it was being read.",
        );
      }
    };

    const interval = setInterval(() => void tick(), POLL_MS);
    // Ask straight away: a second of blank status at the start reads as a
    // click that did nothing.
    void tick();

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [jobId, finish]);

  /** Shared tail of upload and language-choice: both return a job or a document. */
  const accept = useCallback(
    (accepted: UploadAccepted) => {
      // A cache hit skips every paid call and comes back finished.
      if (accepted.state === "ready" && accepted.doc_id) {
        finish({
          state: "ready",
          stage: "ready",
          doc_id: accepted.doc_id,
          job_id: accepted.job_id,
        });
        return;
      }
      if (!accepted.job_id) {
        // Nothing to poll and nothing finished: say so rather than sit on a
        // status line that will never change.
        setBusy(false);
        setSending(null);
        setError("The page was accepted but the server did not say where to follow it.");
        return;
      }
      setJobId(accepted.job_id);
    },
    [finish],
  );

  const begin = useCallback((status: string) => {
    setError(null);
    setJob(null);
    setJobId(null);
    setSending(status);
    setBusy(true);
  }, []);

  const fail = useCallback((cause: unknown, fallback: string) => {
    setBusy(false);
    setSending(null);
    setError(cause instanceof ApiError ? cause.message : fallback);
  }, []);

  const upload = useCallback(
    (file: File) => {
      // A new file abandons any half-answered language question.
      setPendingDocId(null);
      begin("Sending the page…");
      uploadDocument(file)
        .then(accept)
        .catch((cause: unknown) => fail(cause, "That file could not be uploaded."));
    },
    [accept, begin, fail],
  );

  const chooseLanguage = useCallback(
    (docId: string, language: string) => {
      begin(`Re-reading in ${languageName(language)}…`);
      setDocumentLanguage(docId, language)
        .then(accept)
        .catch((cause: unknown) =>
          fail(cause, "That language could not be applied to this page."),
        );
    },
    [accept, begin, fail],
  );

  const reset = useCallback(() => {
    setJobId(null);
    setJob(null);
    setBusy(false);
    setSending(null);
    setError(null);
    setPendingDocId(null);
  }, []);

  return {
    job,
    message: job ? (stageMessage(job) ?? sending) : sending,
    busy,
    error,
    needsLanguage: pendingDocId !== null && !busy,
    pendingDocId,
    upload,
    chooseLanguage,
    reset,
  };
}
