import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'RAG GPT Chat',
  description: 'Perplexica-like chat shell for RAG_GPTV1.0'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
