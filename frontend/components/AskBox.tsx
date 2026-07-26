"use client";

import { askPlaceholder } from "@/lib/languages";
import { useVoiceInput } from "@/lib/useVoiceInput";

interface AskBoxProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  /** The page being read — the recogniser is told its language, not left to guess. */
  docId: string;
  /** The page's language, so the prompt is in the script the reader reads. */
  language?: string | null;
  disabled?: boolean;
  pending?: boolean;
  error?: string | null;
}

const MIC_LABEL: Record<string, string> = {
  idle: "Ask out loud",
  recording: "Stop recording",
  transcribing: "Writing down what you said",
};

/**
 * One box for anything the reader types — or says.
 *
 * A question or a statement — the backend decides which, and its reply says
 * so. Splitting them into two controls would make the reader classify their
 * own sentence before they are allowed to say it.
 */
export function AskBox({
  value,
  onChange,
  onSubmit,
  docId,
  language,
  disabled,
  pending,
  error,
}: AskBoxProps) {
  const voice = useVoiceInput({
    docId,
    // Straight into the box, never straight into a question. A misheard
    // sentence asked on the reader's behalf comes back as a fully verified
    // citation for something they never said.
    onTranscript: (text) => onChange(value ? `${value} ${text}` : text),
  });

  const recording = voice.status === "recording";
  const busy = voice.status === "transcribing";

  return (
    <div className="shrink-0 border-t border-rule px-5 py-4">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <label htmlFor="question" className="sr-only">
          Ask this page
        </label>
        <div className="flex gap-2">
          {voice.supported && (
            <button
              type="button"
              onClick={voice.toggle}
              disabled={disabled || busy}
              aria-label={MIC_LABEL[voice.status]}
              aria-pressed={recording}
              title={MIC_LABEL[voice.status]}
              className={`shrink-0 border px-3 py-2 transition-colors disabled:opacity-40 ${
                recording
                  ? "border-seal bg-seal-wash text-seal"
                  : "border-rule bg-surface text-muted hover:border-duplicator hover:text-duplicator"
              }`}
            >
              {busy ? (
                <span className="text-[0.7rem] font-medium">…</span>
              ) : (
                <MicGlyph recording={recording} />
              )}
            </button>
          )}

          <input
            id="question"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={recording ? "Listening…" : askPlaceholder(language)}
            disabled={disabled}
            className="font-indic min-w-0 flex-1 border border-rule bg-surface px-3 py-2 text-sm outline-none placeholder:text-faint focus:border-duplicator disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={disabled || !value.trim()}
            className="shrink-0 bg-duplicator px-4 py-2 text-xs font-medium text-white transition-opacity disabled:opacity-40"
          >
            {pending ? "Checking…" : "Ask"}
          </button>
        </div>
      </form>

      {/* Said out loud, written down, and left for the reader to check before
          it is asked. The pause is the point. */}
      {recording && (
        <p className="mt-2 text-xs text-faint">
          Listening. Tap again when you&apos;re done — you can edit it before asking.
        </p>
      )}

      {(error || voice.error) && (
        <p
          role="alert"
          className="mt-3 border-l-2 border-seal bg-seal-wash px-3 py-2 text-xs text-seal"
        >
          {error || voice.error}
        </p>
      )}
    </div>
  );
}

function MicGlyph({ recording }: { recording: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      aria-hidden="true"
      className={`h-4 w-4 ${recording ? "animate-pulse" : ""}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
    >
      <rect x="5.75" y="1.75" width="4.5" height="8" rx="2.25" />
      <path d="M3.25 7.5a4.75 4.75 0 0 0 9.5 0M8 12.25V14.25" />
    </svg>
  );
}
