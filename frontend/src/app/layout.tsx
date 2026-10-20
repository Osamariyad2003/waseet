import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Waseet — AI-mediated escrow",
  description:
    "A buyer funds a deal, the platform holds the money, and an AI verifies the seller's deliverable against agreed criteria.",
};

/** The locale layout sets <html>; this one only carries metadata. */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
