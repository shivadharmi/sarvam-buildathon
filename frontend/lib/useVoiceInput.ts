"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { transcribe } from "./api";

export type VoiceStatus = "idle" | "recording" | "transcribing";

/**
 * Formats in preference order. Sarvam's recogniser accepts webm, opus, m4a and
 * ogg directly, which is every format a browser will hand us — so nothing is
 * transcoded on the way out.
 */
const FORMATS = [
  { mime: "audio/webm;codecs=opus", ext: "webm" },
  { mime: "audio/webm", ext: "webm" },
  { mime: "audio/mp4", ext: "m4a" },
  { mime: "audio/ogg;codecs=opus", ext: "ogg" },
] as const;

/**
 * The synchronous endpoint tops out at 30 seconds, so we stop before it does.
 * A recording cut short with the words kept beats one rejected whole.
 */
const MAX_MS = 28_000;

function pickFormat() {
  if (typeof MediaRecorder === "undefined") return null;
  return (
    FORMATS.find((format) => MediaRecorder.isTypeSupported(format.mime)) ?? {
      mime: "",
      ext: "webm",
    }
  );
}

const DENIED =
  "I can't hear the microphone. Allow mic access in your browser, or type the question instead.";

interface VoiceInputOptions {
  docId: string;
  /**
   * Called with what we heard. It belongs in the input box, not in a request —
   * the reader has to see the words before they are asked.
   */
  onTranscript: (text: string) => void;
}

/**
 * Push-to-talk for the question box.
 *
 * The recorder never submits. It fills the box and stops, because a misheard
 * question that is asked anyway comes back as a properly verified citation for
 * something the reader never said — every signal on screen reading "verified",
 * and the answer still wrong. Making the transcript visible first turns a
 * silent failure into an obvious one.
 */
export function useVoiceInput({ docId, onTranscript }: VoiceInputOptions) {
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [supported, setSupported] = useState(false);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Checked after mount: the server has no MediaRecorder, and rendering the
  // button differently on each side would be a hydration mismatch.
  useEffect(() => {
    setSupported(
      typeof navigator !== "undefined" &&
        !!navigator.mediaDevices?.getUserMedia &&
        typeof MediaRecorder !== "undefined",
    );
  }, []);

  const releaseMic = useCallback(() => {
    recorderRef.current?.stream.getTracks().forEach((track) => track.stop());
    recorderRef.current = null;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
  }, []);

  // The browser keeps showing "recording" until the tracks are stopped, so
  // navigating away mid-recording must not leave the mic live.
  useEffect(() => releaseMic, [releaseMic]);

  const stop = useCallback(() => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }, []);

  const start = useCallback(async () => {
    setError(null);

    const format = pickFormat();
    if (!format) {
      setError("This browser can't record audio. Type the question instead.");
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError(DENIED);
      return;
    }

    const recorder = new MediaRecorder(
      stream,
      format.mime ? { mimeType: format.mime } : undefined,
    );
    recorderRef.current = recorder;

    const chunks: BlobPart[] = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };

    recorder.onstop = async () => {
      releaseMic();
      const audio = new Blob(chunks, { type: format.mime || "audio/webm" });

      // A tap rather than a hold. Nothing was said, so there is nothing to
      // report and nothing to pay for.
      if (audio.size < 1024) {
        setStatus("idle");
        return;
      }

      setStatus("transcribing");
      try {
        onTranscript(await transcribe(docId, audio, `question.${format.ext}`));
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Couldn't transcribe that.");
      } finally {
        setStatus("idle");
      }
    };

    recorder.start();
    setStatus("recording");
    timerRef.current = setTimeout(stop, MAX_MS);
  }, [docId, onTranscript, releaseMic, stop]);

  const toggle = useCallback(() => {
    if (status === "recording") stop();
    else if (status === "idle") void start();
  }, [start, status, stop]);

  return { status, error, supported, toggle, clearError: () => setError(null) };
}
