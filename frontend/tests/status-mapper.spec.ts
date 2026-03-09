import { expect, test } from '@playwright/test';
import { mapConnectionStatus, mapPipelineStageState, mapRuntimeLevel, shortRunId } from '../lib/status-mapper';

test.describe('status-mapper', () => {
  test('falls back to unknown for unrecognized pipeline states', () => {
    const mapped = mapPipelineStageState('mystery_state');
    expect(mapped).toEqual({ label: '未知', icon: '🟡', tone: 'warning' });
  });

  test('treats null and empty pipeline states as not started', () => {
    expect(mapPipelineStageState(null)).toEqual({ label: '待处理', icon: '⚪️', tone: 'idle' });
    expect(mapPipelineStageState('')).toEqual({ label: '待处理', icon: '⚪️', tone: 'idle' });
  });

  test('maps connection status with case and whitespace normalization', () => {
    expect(mapConnectionStatus('Connected')).toEqual({ connected: true, label: '已连接' });
    expect(mapConnectionStatus(' connected  ')).toEqual({ connected: true, label: '已连接' });
    expect(mapConnectionStatus('Connection error')).toEqual({ connected: false, label: '连接异常' });
    expect(mapConnectionStatus('offline')).toEqual({ connected: false, label: '未连接' });
  });

  test('falls back to ERROR runtime view for unknown runtime level', () => {
    const mapped = mapRuntimeLevel('NOT_A_LEVEL' as never);
    expect(mapped).toEqual({ label: '状态异常', icon: '🚨', tone: 'text-slate-700 bg-slate-100 border-slate-300' });
  });

  test('shortRunId truncates and handles empty input', () => {
    expect(shortRunId('import_af09c9e2f3d54')).toBe('import_a...');
    expect(shortRunId('abc', 8)).toBe('abc');
    expect(shortRunId('')).toBe('-');
  });
});
