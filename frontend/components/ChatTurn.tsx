"use client";

import { useState } from "react";

import type { AnswerRecord, RefusalReason, SpeechSource } from "@/lib/types";
import { useSpeech } from "@/lib/useSpeech";

/**
 * What the reader is told when an answer does not stand.
 *
 * Only "document_silent" may say the page doesn't say it. The others are
 * limits of ours, and wording them as silence would tell the reader the page
 * lacks something it contains — which is the failure this product exists to
 * prevent. Each gets its own words, and the two that are recoverable say how.
 */
const REFUSALS: Record<RefusalReason, { headline: string; detail: string }> = {
  document_silent: {
    headline: "This page doesn't say.",
    detail: "No line here answers that, so nothing is quoted.",
  },
  not_relevant: {
    headline: "This page doesn't say.",
    detail: "Nothing here answers that question, so nothing is quoted.",
  },
  citation_invalid: {
    headline: "Couldn't verify a citation.",
    detail:
      "The answer couldn't be pinned to specific lines on this page, so it isn't shown. Try asking again, or more specifically.",
  },
};

const UNKNOWN_REFUSAL = {
  headline: "No answer shown.",
  detail: "This one couldn't be backed by a line on the page.",
};

interface ChatTurnProps {
  record: AnswerRecord;
  gloss?: string;
  isActive: boolean;
  onSelect: () => void;
}

/**
 * One exchange in the thread: the question asked, and the verified reply.
 *
 * Cited and refused replies carry equal visual weight on purpose. A refusal is
 * a result here, not an error -- styling it as a failure would undercut the one
 * thing this product claims to do well.
 */
export function ChatTurn({ record, gloss, isActive, onSelect }: ChatTurnProps) {
  const speech = useSpeech(record.doc_id);
  const cited = record.status === "cited";
  const refusal =
    (record.refusal_reason && REFUSALS[record.refusal_reason]) || UNKNOWN_REFUSAL;
  const lineLabel =
    record.quote_from_line === record.quote_to_line
      ? `Line ${record.quote_from_line}`
      : `Lines ${record.quote_from_line}–${record.quote_to_line}`;

  return (
    <li className="px-5 py-4">
      {/* The question, as asked. */}
      <div className="flex justify-end">
        <div className="max-w-[85%] bg-surface px-3 py-2">
          <p className="font-indic text-right text-[0.875rem] leading-snug text-ink">
            {record.question}
          </p>
          {gloss && <p className="mt-0.5 text-right text-xs text-faint">{gloss}</p>}
        </div>
      </div>

      {/* The reply. Clicking it takes the page back to those lines. */}
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={isActive}
        // Active state is neutral on purpose: violet means "from the
        // document" everywhere else, and washing a refusal in it would say
        // the opposite of what happened.
        className={`mt-2.5 w-full border-l-2 py-1.5 pl-3 text-left transition-colors ${
          cited ? "border-duplicator" : "border-seal"
        } ${isActive ? "bg-surface" : "hover:bg-surface/60"}`}
      >
        {cited ? (
          <>
            <p className="font-indic text-[0.875rem] leading-relaxed text-ink">
              {record.answer}
            </p>
            <p className="eyebrow mt-2 text-duplicator">
              {lineLabel} of this page
              {/* A wide citation is a real one and a weak one. Saying which
                  costs nothing; refusing it cost the reader the answer. */}
              {record.citation_is_broad && (
                <span className="text-faint">
                  {" · "}
                  {record.quote_line_count} lines, a large part of it
                </span>
              )}
            </p>
          </>
        ) : (
          <>
            <p className="text-[0.875rem] font-medium text-seal">{refusal.headline}</p>
            <p className="mt-1 text-xs leading-relaxed text-faint">{refusal.detail}</p>
          </>
        )}

        {record.model_quote_matched === false && (
          <p className="mt-2 text-xs leading-relaxed text-faint">
            The model&apos;s wording differed from the lines it pointed at. The lines
            are shown as they appear on the page.
          </p>
        )}
      </button>

      {/* Audio, only where the text is in the document's own language.
          A refusal is written in ours, so there is nothing here to read out.

          Two controls, never one: heard rather than seen, the answer and the
          citation are indistinguishable, and the whole product rests on the
          reader knowing which is which. The labels carry that distinction. */}
      {cited && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 pl-3">
          <ListenButton
            source="answer"
            label="Hear the answer"
            speech={speech}
            onPlay={() => speech.play({ source: "answer", text: record.answer })}
          />
          <ListenButton
            source="quote"
            label={`Hear ${lineLabel.toLowerCase()}, as written`}
            speech={speech}
            onPlay={() =>
              speech.play({
                source: "quote",
                // Offsets, not text. The backend re-slices from its own copy,
                // so this button cannot put words in the page's mouth.
                quoteStart: record.quote_start,
                quoteEnd: record.quote_end,
              })
            }
          />
        </div>
      )}

      {/* The record is the artifact, so sharing it shares the proof: the link
          opens the answer beside the page, with the citation re-checked. */}
      {record.record_id && <ShareButton recordId={record.record_id} />}

      {/* Audio that just stops looks exactly like a page that just ends. */}
      {(speech.truncated.answer || speech.truncated.quote) && (
        <p className="mt-1.5 pl-3 text-xs text-faint">
          That was too long to read in full — the audio stops early. The text above
          is complete.
        </p>
      )}

      {speech.error && (
        <p role="alert" className="mt-1.5 pl-3 text-xs text-seal">
          {speech.error}
        </p>
      )}
    </li>
  );
}

interface ListenButtonProps {
  source: SpeechSource;
  label: string;
  speech: ReturnType<typeof useSpeech>;
  onPlay: () => void;
}

function ListenButton({ source, label, speech, onPlay }: ListenButtonProps) {
  const isLoading = speech.loading === source;
  const isPlaying = speech.active === source;
  const quote = source === "quote";

  return (
    <button
      type="button"
      onClick={onPlay}
      aria-label={label}
      className={`eyebrow flex items-center gap-1 border px-2 py-1 transition-colors ${
        isPlaying || isLoading
          ? "border-duplicator text-duplicator"
          : "border-rule text-faint hover:border-duplicator hover:text-duplicator"
      }`}
    >
      <SpeakerGlyph playing={isPlaying} />
      {isLoading ? "Reading…" : isPlaying ? "Stop" : quote ? "The page" : "The answer"}
    </button>
  );
}

function SpeakerGlyph({ playing }: { playing: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      aria-hidden="true"
      className={`h-3 w-3 ${playing ? "animate-pulse" : ""}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinejoin="round"
    >
      <path d="M8.5 2.5 4.75 5.5H2.25v5h2.5l3.75 3z" />
      <path d="M11 5.75a3 3 0 0 1 0 4.5" strokeLinecap="round" />
    </svg>
  );
}

/**
 * Copy a link to this answer.
 *
 * Offered on refusals as well as citations. "This page doesn't say" is a
 * result, and often the most useful thing a reader can forward to whoever told
 * them it did.
 */
function ShareButton({ recordId }: { recordId: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <div className="mt-1.5 pl-3">
      <button
        type="button"
        onClick={async () => {
          const url = `${window.location.origin}/r/${recordId}`;
          try {
            await navigator.clipboard.writeText(url);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
          } catch {
            // Clipboard is blocked outside a secure context. Show the link so
            // it can still be copied by hand rather than failing silently.
            window.prompt("Copy this link", url);
          }
        }}
        className="eyebrow text-faint underline-offset-2 transition-colors hover:text-duplicator hover:underline"
      >
        {copied ? "Link copied" : "Copy link to this answer"}
      </button>
    </div>
  );
}
