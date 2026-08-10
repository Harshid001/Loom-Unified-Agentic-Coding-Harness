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
      <body className="bg-[#0B0F19] text-gray-100 antialiased min-h-screen">
        {children}
      </body>
    </html>
  );
}
