import Link from "next/link";

interface AppHeaderProps {
  /** Show the way back to the library. Every reader page needs one. */
  back?: boolean;
}

/**
 * The one line the product is willing to promise, on every page.
 *
 * It states the refusal up front rather than as an apology later: a reader who
 * is told before asking that the page may simply not say can read a refusal as
 * an answer instead of a failure.
 */
export function AppHeader({ back }: AppHeaderProps) {
  return (
    <header className="flex shrink-0 flex-wrap items-baseline gap-x-6 gap-y-2 border-b border-rule px-6 py-4">
      <Link href="/" className="text-[0.9375rem] font-semibold tracking-tight">
        Ask the Document
      </Link>
      <p className="text-xs text-muted">
        Every answer shows the line it came from — or says the page doesn&apos;t say.
      </p>

      {back && (
        <Link
          href="/"
          className="ml-auto px-3 py-1.5 text-xs text-muted transition-colors hover:bg-surface hover:text-ink"
        >
          ← All documents
        </Link>
      )}
    </header>
  );
}
