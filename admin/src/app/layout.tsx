import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Waseet Admin — Operations",
  description: "Reviewer operations console for Waseet escrow: dashboard and dispute resolution.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
