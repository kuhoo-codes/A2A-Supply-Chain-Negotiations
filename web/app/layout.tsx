import type { Metadata } from "next";
import Link from "next/link";

import { RunSelector } from "../components/run-selector";
import { getRuns } from "../lib/api";
import "./globals.css";


export const metadata: Metadata = {
  title: "Tomato Negotiations",
  description: "Base scaffold for supply chain negotiation runs.",
};


export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const runsResult = await getRuns();
  const runs = runsResult.data ?? [];

  return (
    <html lang="en">
      <body>
        <div className="shell page">
          <header className="topbar">
            <Link className="brand" href="/">
              Tomato Negotiations
            </Link>
            <div className="topbar-tools">
              {runs.length > 0 ? <RunSelector runs={runs} variant="nav" /> : null}
              <nav className="nav">
                <Link href="/">Home</Link>
                <Link href="/runs">Runs</Link>
              </nav>
            </div>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
