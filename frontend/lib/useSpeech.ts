"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { speak } from "./api";
import type { SpeechSource } from "./types";

/**
 * The one clip playing anywhere on the page.
 *
 * Module-level rather than per-hook: every answer in the thread mounts its own
 * buttons, and two answers talking over each other would make it impossible to
 * tell which one you were hearing — the audio equivalent of losing the line
 * numbers.
 */
let playing: HTMLAudioElement | null = null;

function silence() {
  playing?.pause();
  playing = null;
}

interface SpeakTarget {
  source: SpeechSource;
  quoteStart?: number | null;
  quoteEnd?: number | null;
  text?: string;
}

/**
 * Fetch-on-click playback for one answer's audio.
 *
 * Nothing is synthesised until asked for: speech is a paid call and most
 * answers are read, not heard. Once fetched, clips are kept for the life of
 * the component so replaying is free.
 */
export function useSpeech(docId: string) {
  const [active, setActive] = useState<SpeechSource | null>(null);
  const [loading, setLoading] = useState<SpeechSource | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Which sources came back shortened. Never cleared on stop -- once we know
  // the reader did not hear all of it, that stays true.
  const [truncated, setTruncated] = useState<Partial<Record<SpeechSource, boolean>>>({});

  const clips = useRef<Partial<Record<SpeechSource, string[]>>>({});
  // Bumped on every stop, so audio from an abandoned request never starts.
  const generation = useRef(0);

  useEffect(() => silence, []);

  const stop = useCallback(() => {
    generation.current += 1;
    silence();
    setActive(null);
    setLoading(null);
  }, []);

  const play = useCallback(
    async (target: SpeakTarget) => {
      const { source } = target;

      // A second click on a playing button means stop.
      if (active === source || loading === source) {
        stop();
        return;
      }

      generation.current += 1;
      const mine = generation.current;
      const isStale = () => generation.current !== mine;

      silence();
      setError(null);
      setLoading(source);

      try {
        let audios = clips.current[source];
        if (!audios) {
          const speech = await speak(docId, target);
          audios = speech.audios;
          clips.current[source] = audios;
          if (speech.truncated) setTruncated((prior) => ({ ...prior, [source]: true }));
        }
        if (isStale()) return;

        setLoading(null);
        setActive(source);

        for (const clip of audios) {
          if (isStale()) return;
          await new Promise<void>((resolve, reject) => {
            const audio = new Audio(`data:audio/wav;base64,${clip}`);
            playing = audio;
            audio.onended = () => resolve();
            audio.onerror = () => reject(new Error("This audio wouldn't play."));
            audio.play().catch(reject);
          });
        }
      } catch (caught) {
        if (isStale()) return;
        setError(caught instanceof Error ? caught.message : "Couldn't read that aloud.");
      } finally {
        if (!isStale()) {
          setActive(null);
          setLoading(null);
        }
      }
    },
    [active, docId, loading, stop],
  );

  return { play, stop, active, loading, error, truncated };
}
