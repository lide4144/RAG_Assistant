'use client';

import { useState } from 'react';
import type { MutableRefObject } from 'react';
import { resolveKernelApiUrl } from '../lib/deployment-endpoints';
import type { PipelineTaskPanelState, PipelineTaskState } from './PipelineWorkbenchPanel';

type TaskWsPayload =
  | {
      type: 'taskState';
      taskId: string;
      taskKind: 'graph_build';
      state: PipelineTaskState;
      accepted?: boolean;
      updatedAt: string;
    }
  | {
      type: 'taskProgress';
      taskId: string;
      taskKind: 'graph_build';
      state: PipelineTaskState;
      stage: string;
      processed: number;
      total: number;
      elapsedMs: number;
      message: string;
      updatedAt: string;
    }
  | {
      type: 'taskResult';
      taskId: string;
      taskKind: 'graph_build';
      state: PipelineTaskState;
      result?: Record<string, unknown>;
      error?: { stage: string; message: string; recovery: string };
      updatedAt: string;
    }
  | {
      type: 'taskError';
      taskId: string;
      taskKind: 'graph_build';
      state: 'failed';
      error: { stage: string; message: string; recovery: string };
      updatedAt: string;
    };

interface UsePipelineWorkbenchOptions {
  wsRef: MutableRefObject<WebSocket | null>;
  statusText: string;
}

export function usePipelineWorkbench({ wsRef, statusText }: UsePipelineWorkbenchOptions) {
  const [taskPanel, setTaskPanel] = useState<PipelineTaskPanelState | null>(null);

  const applyTaskPayload = (payload: TaskWsPayload): boolean => {
    if (payload.type === 'taskState') {
      setTaskPanel((prev) => ({
        taskId: payload.taskId,
        state: payload.state,
        stage: prev?.stage ?? payload.state,
        processed: prev?.processed ?? 0,
        total: prev?.total ?? 0,
        elapsedMs: prev?.elapsedMs ?? 0,
        message: prev?.message ?? '',
        updatedAt: payload.updatedAt,
        accepted: payload.accepted,
        error: prev?.error,
        result: prev?.result
      }));
      return true;
    }
    if (payload.type === 'taskProgress') {
      setTaskPanel((prev) => ({
        taskId: payload.taskId,
        state: payload.state,
        stage: payload.stage,
        processed: payload.processed,
        total: payload.total,
        elapsedMs: payload.elapsedMs,
        message: payload.message,
        updatedAt: payload.updatedAt,
        accepted: prev?.accepted,
        error: prev?.error,
        result: prev?.result
      }));
      return true;
    }
    if (payload.type === 'taskResult') {
      setTaskPanel((prev) => ({
        taskId: payload.taskId,
        state: payload.state,
        stage: prev?.stage ?? payload.state,
        processed: prev?.processed ?? 0,
        total: prev?.total ?? 0,
        elapsedMs: prev?.elapsedMs ?? 0,
        message: prev?.message ?? (payload.state === 'succeeded' ? '任务完成' : '任务失败'),
        updatedAt: payload.updatedAt,
        accepted: prev?.accepted,
        error: payload.error,
        result: payload.result
      }));
      return true;
    }
    if (payload.type === 'taskError') {
      setTaskPanel((prev) => ({
        taskId: payload.taskId,
        state: 'failed',
        stage: payload.error.stage || prev?.stage || 'failed',
        processed: prev?.processed ?? 0,
        total: prev?.total ?? 0,
        elapsedMs: prev?.elapsedMs ?? 0,
        message: payload.error.message || prev?.message || '任务失败',
        updatedAt: payload.updatedAt,
        accepted: prev?.accepted,
        error: payload.error,
        result: prev?.result
      }));
      return true;
    }
    return false;
  };

  const startGraphBuildTask = (options?: { llmMaxConcurrency?: number }) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setTaskPanel((prev) => ({
        taskId: prev?.taskId ?? '',
        state: 'failed',
        stage: prev?.stage ?? 'start',
        processed: prev?.processed ?? 0,
        total: prev?.total ?? 0,
        elapsedMs: prev?.elapsedMs ?? 0,
        message: 'WebSocket 未连接，无法启动任务',
        updatedAt: new Date().toISOString(),
        accepted: prev?.accepted,
        error: {
          stage: 'start',
          message: 'WebSocket not connected',
          recovery: '请确认 Gateway 已启动后重试'
        },
        result: prev?.result
      }));
      return;
    }
    wsRef.current.send(
      JSON.stringify({
        type: 'task_start_graph_build',
        payload: options?.llmMaxConcurrency
          ? { llm_max_concurrency: Math.max(1, Math.min(32, Math.floor(options.llmMaxConcurrency))) }
          : {}
      })
    );
    setTaskPanel((prev) => ({
      taskId: prev?.taskId ?? '',
      state: 'queued',
      stage: 'queued',
      processed: 0,
      total: 0,
      elapsedMs: 0,
      message: '图构建任务已提交',
      updatedAt: new Date().toISOString(),
      accepted: true,
      error: undefined,
      result: undefined
    }));
  };

  const retryGraphBuildTask = (options?: { llmMaxConcurrency?: number }) => {
    startGraphBuildTask(options);
  };

  const cancelGraphBuildTask = () => {
    if (!taskPanel?.taskId) {
      return;
    }
    void (async () => {
      try {
        const response = await fetch(resolveKernelApiUrl(`/api/tasks/${taskPanel.taskId}/cancel`), { method: 'POST' });
        if (!response.ok) {
          throw new Error(`取消任务失败 (${response.status})`);
        }
        const now = new Date().toISOString();
        setTaskPanel((prev) =>
          prev
            ? {
                ...prev,
                state: 'cancelled',
                stage: 'cancelled',
                message: '任务已取消',
                updatedAt: now
              }
            : prev
        );
      } catch (error) {
        const message = error instanceof Error ? error.message : '取消任务失败';
        setTaskPanel((prev) => ({
          taskId: prev?.taskId ?? '',
          state: prev?.state ?? 'failed',
          stage: prev?.stage ?? 'cancel',
          processed: prev?.processed ?? 0,
          total: prev?.total ?? 0,
          elapsedMs: prev?.elapsedMs ?? 0,
          message,
          updatedAt: new Date().toISOString(),
          accepted: prev?.accepted,
          error: {
            stage: 'cancel',
            message,
            recovery: '请稍后重试'
          },
          result: prev?.result
        }));
      }
    })();
  };

  return {
    taskPanel,
    applyTaskPayload,
    startGraphBuildTask,
    retryGraphBuildTask,
    cancelGraphBuildTask,
    canStartTask: statusText === 'Connected'
  };
}
