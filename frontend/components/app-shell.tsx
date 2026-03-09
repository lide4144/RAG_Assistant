'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BotMessageSquare, ChevronDown, DatabaseZap, Settings2 } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import type { RuntimeLevel, RuntimeOverview } from '../lib/types';
import { fetchAdminJson } from '../lib/admin-http';
import { mapConnectionStatus, mapRuntimeLevel } from '../lib/status-mapper';

type NavItem = {
  href: string;
  label: string;
  icon: typeof BotMessageSquare;
};

const navItems: NavItem[] = [
  { href: '/chat', label: '对话问答', icon: BotMessageSquare },
  { href: '/pipeline', label: '知识处理', icon: DatabaseZap },
  { href: '/settings', label: '模型设置', icon: Settings2 }
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [runtimeOverview, setRuntimeOverview] = useState<RuntimeOverview | null>(null);
  const [statusLoadFailed, setStatusLoadFailed] = useState(false);
  const [alertExpanded, setAlertExpanded] = useState(false);
  const [runtimePollingSuspended, setRuntimePollingSuspended] = useState(false);
  const kernelBaseUrl = process.env.NEXT_PUBLIC_KERNEL_BASE_URL ?? '';
  const importBusyEventName = 'pipeline-import-busy';

  useEffect(() => {
    let mounted = true;
    const loadRuntimeOverview = async () => {
      if (runtimePollingSuspended) {
        return;
      }
      try {
        const result = await fetchAdminJson<RuntimeOverview>(`${kernelBaseUrl}/api/admin/runtime-overview`);
        if (!result.ok) {
          if (mounted) {
            setStatusLoadFailed(true);
          }
          return;
        }
        if (mounted) {
          setRuntimeOverview(result.data);
          setStatusLoadFailed(false);
        }
      } catch {
        if (mounted) {
          setStatusLoadFailed(true);
        }
      }
    };
    void loadRuntimeOverview();
    const timer = window.setInterval(() => void loadRuntimeOverview(), 15000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, [kernelBaseUrl, runtimePollingSuspended]);

  useEffect(() => {
    const onImportBusy = (event: Event) => {
      const customEvent = event as CustomEvent<{ busy?: boolean }>;
      setRuntimePollingSuspended(Boolean(customEvent.detail?.busy));
    };
    window.addEventListener(importBusyEventName, onImportBusy as EventListener);
    return () => window.removeEventListener(importBusyEventName, onImportBusy as EventListener);
  }, []);

  const runtimeState = useMemo(() => {
    if (statusLoadFailed || !runtimeOverview) {
      return {
        level: 'ERROR' as RuntimeLevel,
        reason: '运行态概览加载失败',
        summary: '无法读取当前模型运行态',
      };
    }
    const level = runtimeOverview.status.level;
    const reason = runtimeOverview.status.reasons[0] ?? '运行态正常';
    const answer = runtimeOverview.llm.answer;
    const rerank = runtimeOverview.llm.rerank;
    const rewrite = runtimeOverview.llm.rewrite;
    const summary = `Answer: ${answer.model || '-'} · Rerank: ${rerank.model || '-'} · Rewrite: ${rewrite.model || '-'}`;
    return { level, reason, summary };
  }, [runtimeOverview, statusLoadFailed]);

  const runtimeView = mapRuntimeLevel(runtimeState.level);
  const connection = mapConnectionStatus(statusLoadFailed ? 'Connection error' : 'Connected');
  const fallbackEntries = runtimeOverview?.pipeline?.marker_llm?.summary_fields ?? [];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto flex min-h-screen w-full max-w-[1440px] gap-4 p-3 md:gap-6 md:p-6">
        <div className="fixed inset-x-3 top-3 z-30 rounded-2xl border border-slate-200 bg-white/95 p-2 shadow md:hidden">
          <nav className="grid grid-cols-3 gap-1">
            {navItems.map((item) => {
              const active = pathname.startsWith(item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={`mobile-${item.href}`}
                  href={item.href}
                  data-testid={`nav-${item.href.replace('/', '')}-link`}
                  className={`flex items-center justify-center gap-1 rounded-xl px-2 py-2 text-xs font-medium ${
                    active ? 'bg-slate-900 text-white' : 'text-slate-600'
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>
        <aside className="hidden w-72 shrink-0 overflow-hidden rounded-3xl border border-slate-200 bg-gradient-to-b from-white to-slate-100 shadow-lg md:flex md:flex-col">
          <div className="border-b border-slate-200 px-5 py-6">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">RAG SaaS</p>
            <h1 className="mt-2 text-xl font-semibold">研究助理工作台</h1>
            <p className="mt-2 text-sm text-slate-600">统一对话、知识库构建流水线与模型配置管理。</p>
          </div>
          <nav className="flex-1 space-y-1 px-3 py-4">
            {navItems.map((item) => {
              const active = pathname.startsWith(item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  data-testid={`nav-${item.href.replace('/', '')}-link`}
                  className={`group flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition ${
                    active
                      ? 'bg-slate-900 text-white shadow'
                      : 'text-slate-700 hover:bg-white hover:text-slate-900 hover:shadow-sm'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
          <div className="border-t border-slate-200 bg-white/80 px-4 py-4 text-xs text-slate-500">
            版本 1.0 · 现代化 SaaS 信息架构
          </div>
        </aside>

        <main className="min-w-0 flex-1 pt-16 md:pt-0">
          <div data-testid="global-runtime-status" className="mb-4 space-y-2">
            <div className="flex items-center justify-end">
              <span className="inline-flex items-center gap-2 text-xs text-slate-600">
                <span
                  className={`h-2.5 w-2.5 rounded-full ${connection.connected ? 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.65)]' : 'bg-slate-400'}`}
                  aria-hidden
                />
                {connection.connected ? '🟢 已连接' : '⚪ 未连接'}
              </span>
            </div>

            {runtimeState.level === 'DEGRADED' ? (
              <div className={`rounded-2xl border px-3 py-2 text-xs ${runtimeView.tone}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">⚠️ 系统当前处于降级运行状态 (DEGRADED)</span>
                  <button
                    type="button"
                    onClick={() => setAlertExpanded((prev) => !prev)}
                    className="inline-flex items-center gap-1 rounded-lg border border-amber-300 bg-white/70 px-2 py-1 text-[11px] font-medium text-amber-800"
                  >
                    查看详情
                    <ChevronDown className={`h-3.5 w-3.5 transition ${alertExpanded ? 'rotate-180' : ''}`} />
                  </button>
                  <Link href="/settings" className="ml-auto text-[11px] font-semibold underline underline-offset-2">
                    前往模型设置
                  </Link>
                </div>
                {alertExpanded ? (
                  <ul className="mt-2 grid list-disc gap-x-5 gap-y-1 pl-5 text-[11px] text-amber-900 md:grid-cols-2">
                    {fallbackEntries.length ? (
                      fallbackEntries.map((item) => (
                        <li key={item.field}>
                          <span className="font-medium">{item.field}</span>: {String(item.value)}
                        </li>
                      ))
                    ) : (
                      <li>{runtimeOverview?.pipeline.last_ingest?.fallback_reason || '暂无降级参数明细'}</li>
                    )}
                  </ul>
                ) : null}
              </div>
            ) : (
              <div className={`rounded-2xl border px-3 py-2 text-xs ${runtimeView.tone}`}>
                <span className="font-semibold">
                  {runtimeView.icon} {runtimeView.label}
                </span>
                <span className="ml-2 text-[11px]">{runtimeState.reason}</span>
                {runtimePollingSuspended ? <span className="ml-2 text-[11px]">导入进行中，已暂停运行态轮询</span> : null}
              </div>
            )}
          </div>
          {children}
        </main>
      </div>
    </div>
  );
}
