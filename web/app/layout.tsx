import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ZAO Recordings",
  description: "Review and publish ZAO workshop recordings",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-white/10 px-6 py-4">
          <h1 className="text-xl font-bold" style={{ color: "var(--orange)" }}>
            ZAO Recordings
          </h1>
          <p className="text-sm text-white/50">Review, cut, and publish - the Descript replacement</p>
        </header>
        <main className="mx-auto max-w-5xl p-6">{children}</main>
      </body>
    </html>
  );
}
