'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BotMessageSquare, ChevronDown, DatabaseZap, Settings2, Sparkles, Waves, Library } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import type { RuntimeLevel, RuntimeOverview } from '../lib/types';
import { fetchAdminJson } from '../lib/admin-http';
import { resolveAdminUrl } from '../lib/deployment-endpoints';
import { mapConnectionStatus, mapRuntimeLevel } from '../lib/status-mapper';
import { TaskCenterProvider } from './task-center';

type NavItem = {
  href: string;
  label: string;
  icon: typeof BotMessageSquare;
};

const navItems: NavItem[] = [
  { href: '/chat', label: '对话问答', icon: BotMessageSquare },
  { href: '/pipeline', label: '知识处理', icon: DatabaseZap },
  { href: '/library', label: '知识库', icon: Library },
  { href: '/settings', label: '模型设置', icon: Settings2 }
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [runtimeOverview, setRuntimeOverview] = useState<RuntimeOverview | null>(null);
  const [statusLoadFailed, setStatusLoadFailed] = useState(false);
  const [alertExpanded, setAlertExpanded] = useState(false);
  const [runtimePollingSuspended, setRuntimePollingSuspended] = useState(false);
  const runtimeOverviewUrl = useMemo(() => resolveAdminUrl('/api/admin/runtime-overview'), []);
  const importBusyEventName = 'pipeline-import-busy';

  useEffect(() => {
    let mounted = true;
    const loadRuntimeOverview = async () => {
      if (runtimePollingSuspended) {
        return;
      }
      try {
        const result = await fetchAdminJson<RuntimeOverview>(runtimeOverviewUrl);
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
  }, [runtimeOverviewUrl, runtimePollingSuspended]);

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
    <TaskCenterProvider>
      <div className="min-h-screen bg-transparent text-slate-900">
        <div className="mx-auto flex min-h-screen w-full max-w-[1920px] gap-4 p-3 md:gap-6 md:p-6">
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
          <aside className="glass-card hidden w-80 shrink-0 overflow-hidden rounded-[34px] md:flex md:flex-col">
            <div className="border-b border-slate-200/80 px-6 py-6">
              <div className="inline-flex items-center gap-2 rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-700">
                <Waves className="h-3.5 w-3.5" />
                RAG SaaS
              </div>
              <h1 className="mt-4 text-[34px] font-semibold leading-tight tracking-tight text-slate-950">研究助理工作台</h1>
              <p className="mt-3 text-sm leading-6 text-slate-600">把对话问答、知识处理、模型切换整合成一套更适合中文用户的工作流。</p>
              <div className="mt-4 rounded-2xl border border-slate-200 bg-white/80 p-3 text-xs text-slate-600">
                <p className="font-semibold text-slate-900">当前主线</p>
                <p className="mt-1">先导入资料，再在聊天页验证答案，最后用模型设置做精细调整。</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Link
                    href="/settings#llm-log-config"
                    className="inline-flex items-center gap-1 rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 text-[11px] font-medium text-sky-800"
                  >
                    <Settings2 className="h-3.5 w-3.5" />
                    LLM 日志查看与下载
                  </Link>
                </div>
              </div>
            </div>
            <nav className="flex-1 space-y-1 px-4 py-5">
              {navItems.map((item) => {
                const active = pathname.startsWith(item.href);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    data-testid={`nav-${item.href.replace('/', '')}-link`}
                    className={`group flex items-center gap-3 rounded-[22px] px-4 py-3 text-sm font-medium transition ${
                      active
                        ? 'bg-slate-950 text-white shadow-[0_18px_48px_rgba(15,23,42,0.22)]'
                        : 'text-slate-700 hover:bg-white/90 hover:text-slate-900 hover:shadow-sm'
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    <span>{item.label}</span>
                    {active ? <Sparkles className="ml-auto h-4 w-4 text-slate-300" /> : null}
                  </Link>
                );
              })}
            </nav>
            <div className="border-t border-slate-200/80 bg-white/70 px-5 py-4 text-xs text-slate-500">
              版本 1.0 · 中文友好的研究面板
            </div>
          </aside>

          <main className="min-w-0 flex-1 pt-16 md:pt-0">
            <div data-testid="global-runtime-status" className="mb-4 space-y-2">
              <div className="flex items-center justify-end">
                <span className="inline-flex items-center gap-2 rounded-full border border-white/70 bg-white/85 px-3 py-1.5 text-xs text-slate-600 shadow-sm">
                  <span
                    className={`h-2.5 w-2.5 rounded-full ${connection.connected ? 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.65)]' : 'bg-slate-400'}`}
                    aria-hidden
                  />
                  {connection.connected ? '已连接' : '未连接'}
                </span>
              </div>

              {runtimeState.level === 'DEGRADED' ? (
                <div className={`glass-card rounded-[24px] px-4 py-3 text-xs ${runtimeView.tone}`}>
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
                <div className={`glass-card rounded-[24px] px-4 py-3 text-xs ${runtimeView.tone}`}>
                  <span className="font-semibold">
                    {runtimeView.icon} {runtimeView.label}
                  </span>
                  <span className="ml-2 text-[11px]">{runtimeState.reason}</span>
                  {runtimePollingSuspended ? <span className="ml-2 text-[11px]">导入进行中，已暂停运行态轮询</span> : null}
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-600">
                <span className="rounded-full border border-slate-200 bg-white/85 px-3 py-1">
                  LLM 日志: {runtimeOverview?.observability?.llm_logging?.enabled ? '开启' : '关闭'}
                </span>
                <span className="rounded-full border border-slate-200 bg-white/85 px-3 py-1">
                  长度上限: {runtimeOverview?.observability?.llm_logging?.max_body_chars ?? '-'}
                </span>
                <Link href="/settings#llm-log-config" className="font-semibold text-sky-700 underline underline-offset-2">
                  查看日志
                </Link>
              </div>
            </div>
            {children}
          </main>
        </div>
      </div>
    </TaskCenterProvider>
  );
}
