import './globals.css';
import type { Metadata } from 'next';
import { Toaster } from 'sonner';
import { AppShell } from '../components/app-shell';

export const metadata: Metadata = {
  title: '研究助理 SaaS 工作台',
  description: 'RAG_GPTV1.0 现代化前端工作台'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <AppShell>{children}</AppShell>
        <Toaster position="top-right" richColors />
      </body>
    </html>
  );
}
