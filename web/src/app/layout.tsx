import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Loom — Unified Agentic Coding Harness',
  description: 'Model-independent, terminal-first coding agent harness & trace dashboard',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-[var(--bg-root)] text-[var(--text-primary)] antialiased min-h-screen">
        {children}
      </body>
    </html>
  );
}
