"use client";

import { useEffect, useState } from "react";

import { loadStarters } from "./questions";
import type { StarterQuestion } from "./questions";

/**
 * Suggested questions for the open page.
 *
 * @param digitisedAt Re-reading a page in another language produces a new
 *   digitisation, and starters written against the old one describe text that
 *   no longer exists at those lines.
 *
 * Never fails: an empty list is a plain input box, which is a working page.
 */
export function useStarters(
  docId: string,
  digitisedAt?: string | null,
): StarterQuestion[] {
  const [starters, setStarters] = useState<StarterQuestion[]>([]);

  useEffect(() => {
    if (!docId) {
      setStarters([]);
      return;
    }

    let cancelled = false;
    setStarters([]);
    void loadStarters(docId).then((list) => {
      if (!cancelled) setStarters(list);
    });

    return () => {
      cancelled = true;
    };
  }, [docId, digitisedAt]);

  return starters;
}
