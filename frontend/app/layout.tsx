import type { Metadata } from "next";
import {
  IBM_Plex_Mono,
  IBM_Plex_Sans,
  Noto_Sans_Tamil,
  Noto_Sans_Telugu,
} from "next/font/google";
import "./globals.css";

/*
  IBM Plex for the interface: it was drawn as an institution's official voice,
  which is the register here rather than a startup's. Mono carries the line
  numbers, where a fixed advance is functionally required, and the labels.

  Noto covers the document text. Without it, Tamil and Telugu fall back to
  whatever the OS happens to have, which on many machines is nothing.

  ⚠️ KNOWN GAP: uploads accept all 23 digitisation languages, but only these
  two Noto faces are loaded. A Bengali, Kannada or Malayalam page therefore
  hits exactly the fallback described above and can render as tofu boxes.
  Loading 21 more webfonts is the wrong fix -- it would cost far more than it
  buys for a demo whose measured documents are Tamil and Telugu. The right
  fix, when it matters, is to load the face for the DETECTED language only.
*/
const plexSans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

const notoTamil = Noto_Sans_Tamil({
  variable: "--font-noto-tamil",
  subsets: ["tamil"],
  weight: ["400", "500", "600"],
});

const notoTelugu = Noto_Sans_Telugu({
  variable: "--font-noto-telugu",
  subsets: ["telugu"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Ask the Document",
  description:
    "Ask a dense official page a question. Every answer shows the exact line it came from, or says the page doesn't say.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${plexSans.variable} ${plexMono.variable} ${notoTamil.variable} ${notoTelugu.variable} h-full antialiased`}
    >
      <body className="min-h-full">{children}</body>
    </html>
  );
}
