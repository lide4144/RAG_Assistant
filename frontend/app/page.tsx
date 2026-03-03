import Link from 'next/link';

export default function HomePage() {
  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <div className="max-w-xl rounded-2xl border border-black/10 bg-white/80 p-8 shadow-xl backdrop-blur">
        <h1 className="text-3xl font-semibold tracking-tight">RAG GPT Frontend</h1>
        <p className="mt-3 text-sm text-black/70">
          Initial Next.js shell is ready. Enter the chat workspace to start multi-turn messaging.
        </p>
        <Link
          href="/chat"
          className="mt-6 inline-flex rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accentDark"
        >
          Open Chat
        </Link>
      </div>
    </main>
  );
}
