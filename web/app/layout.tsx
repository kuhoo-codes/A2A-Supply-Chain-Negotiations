import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";


export const metadata: Metadata = {
  title: "A2A Supply Chain Negotiations",
  description: "Base scaffold for supply chain negotiation runs.",
};


export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <div className="shell page">
          <header className="topbar">
            <Link className="brand" href="/">
              A2A Negotiations
            </Link>
            <nav className="nav">
              <Link href="/">Home</Link>
              <Link href="/runs">Runs</Link>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
