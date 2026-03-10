'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { resolveGatewayWebSocketUrl } from '../lib/deployment-endpoints';
import { PipelineWorkbenchPanel } from './PipelineWorkbenchPanel';
import { usePipelineWorkbench } from './usePipelineWorkbench';

type TaskPayload = Parameters<ReturnType<typeof usePipelineWorkbench>['applyTaskPayload']>[0];

export function PipelineShell() {
  const router = useRouter();
  const wsRef = useRef<WebSocket | null>(null);
  const [statusText, setStatusText] = useState('Disconnected');
  const wsUrl = useMemo(() => resolveGatewayWebSocketUrl(), []);

  const { taskPanel, applyTaskPayload, startGraphBuildTask, retryGraphBuildTask, cancelGraphBuildTask } =
    usePipelineWorkbench({ wsRef, statusText });
  const applyTaskPayloadRef = useRef(applyTaskPayload);

  useEffect(() => {
    applyTaskPayloadRef.current = applyTaskPayload;
  }, [applyTaskPayload]);

  useEffect(() => {
    if (!wsUrl) {
      setStatusText('Connection error');
      return;
    }

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => setStatusText('Connected');
    ws.onclose = () => setStatusText('Disconnected');
    ws.onerror = () => setStatusText('Connection error');

    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data) as TaskPayload | { type?: string };
      if (
        payload &&
        (payload as { type?: string }).type &&
        ((payload as { type?: string }).type === 'taskState' ||
          (payload as { type?: string }).type === 'taskProgress' ||
          (payload as { type?: string }).type === 'taskResult' ||
          (payload as { type?: string }).type === 'taskError')
      ) {
        applyTaskPayloadRef.current(payload as TaskPayload);
      }
    };

    return () => ws.close();
  }, [wsUrl]);

  return (
    <PipelineWorkbenchPanel
      statusText={statusText}
      taskPanel={taskPanel}
      onStartGraphBuild={startGraphBuildTask}
      onRetryGraphBuild={retryGraphBuildTask}
      onCancelGraphBuild={cancelGraphBuildTask}
      onGoChat={() => router.push('/chat')}
    />
  );
}
