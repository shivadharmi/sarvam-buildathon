import Link from "next/link";

import { AppHeader } from "@/components/AppHeader";
import type { DocumentState } from "@/lib/useDocument";

interface MissingDocumentProps {
  docId: string;
  state: DocumentState;
  /** The server's own words, when the failure was reaching it. */
  error?: string | null;
}

/**
 * An address that does not lead to a document.
 *
 * The two reasons are kept apart, for the same reason a refusal is: "I don't
 * have that document" is a claim about what exists, and saying it when we
 * simply could not ask would be a confident answer to a question we never got
 * to check.
 */
export function MissingDocument({ docId, state, error }: MissingDocumentProps) {
  const unreachable = state === "unreachable";

  return (
    <div className="mx-auto flex min-h-screen max-w-[880px] flex-col">
      <AppHeader back />

      <main className="flex-1 px-6 py-10">
        <p className="text-sm font-medium text-seal">
          {unreachable
            ? "Couldn’t check for that document."
            : "I don’t have that document."}
        </p>

        <p className="mt-2 max-w-[34rem] text-xs leading-relaxed text-muted">
          {unreachable
            ? error ??
              "The backend didn’t answer, so whether this page exists is unknown."
            : "Nothing is stored under this address. An uploaded page is kept on the server, so a link can outlive one — and a mistyped address lands here too."}
        </p>

        {docId && (
          <p className="mt-3 font-mono text-xs text-faint">
            {docId.length > 64 ? `${docId.slice(0, 64)}…` : docId}
          </p>
        )}

        <p className="mt-6">
          <Link
            href="/"
            className="border border-ink px-3 py-2 text-xs font-medium transition-colors hover:bg-ink hover:text-paper"
          >
            ← Back to the library
          </Link>
        </p>
      </main>
    </div>
  );
}
