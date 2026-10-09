import React, { useState, useEffect, useCallback } from 'react';
import { Upload, File, CheckCircle2, Loader2, FileType, X, Trash2, RefreshCw, AlertCircle, Clock } from 'lucide-react';

interface QueueItem {
  id: string;
  file: File;
  status: 'queued' | 'processing' | 'completed' | 'error';
  progress: number;
  errorMessage?: string;
}

const Converter: React.FC = () => {
  const [isDragging, setIsDragging] = useState(false);
  const [queue, setQueue] = useState<QueueItem[]>([]);

  // Helper to format file size
  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // Simulation logic for processing queue
  useEffect(() => {
    const processQueue = () => {
      setQueue(currentQueue => {
        return currentQueue.map(item => {
          if (item.status === 'queued') {
            // Start processing
            simulateProcessing(item.id);
            return { ...item, status: 'processing', progress: 0 };
          }
          return item;
        });
      });
    };
    
    // Check queue every 500ms
    const timer = setInterval(processQueue, 500);
    return () => clearInterval(timer);
  }, []);

  const simulateProcessing = useCallback((itemId: string) => {
    let progress = 0;
    const speed = Math.random() * 2 + 1; // Random speed
    const shouldFail = Math.random() > 0.8; // 20% chance of failure

    const interval = setInterval(() => {
      setQueue(currentQueue => {
        return currentQueue.map(item => {
          if (item.id !== itemId) return item;

          // If previously cancelled or removed
          if (item.status !== 'processing') {
            clearInterval(interval);
            return item;
          }

          const newProgress = item.progress + speed;
          
          if (shouldFail && newProgress > 60) {
             clearInterval(interval);
             return { ...item, status: 'error', errorMessage: '解析格式错误', progress: 60 };
          }

          if (newProgress >= 100) {
            clearInterval(interval);
            return { ...item, status: 'completed', progress: 100 };
          }

          return { ...item, progress: newProgress };
        });
      });
    }, 100);
  }, []);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setIsDragging(true);
    } else if (e.type === 'dragleave') {
      setIsDragging(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      addFilesToQueue(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addFilesToQueue(Array.from(e.target.files));
    }
  };

  const addFilesToQueue = (files: File[]) => {
    const newItems: QueueItem[] = files.map(file => ({
      id: Math.random().toString(36).substring(7),
      file,
      status: 'queued',
      progress: 0
    }));
    setQueue(prev => [...prev, ...newItems]);
  };

  const removeItem = (id: string) => {
    setQueue(prev => prev.filter(item => item.id !== id));
  };

  const retryItem = (id: string) => {
    setQueue(prev => prev.map(item => 
      item.id === id ? { ...item, status: 'queued', progress: 0, errorMessage: undefined } : item
    ));
  };

  const retryAllFailed = () => {
    setQueue(prev => prev.map(item => 
      item.status === 'error' ? { ...item, status: 'queued', progress: 0, errorMessage: undefined } : item
    ));
  };

  const clearCompleted = () => {
    setQueue(prev => prev.filter(item => item.status !== 'completed'));
  };

  const getStatusIcon = (status: QueueItem['status']) => {
    switch (status) {
      case 'completed': return <CheckCircle2 className="w-5 h-5 text-green-400" />;
      case 'error': return <AlertCircle className="w-5 h-5 text-red-400" />;
      case 'processing': return <Loader2 className="w-5 h-5 text-cyan-400 animate-spin" />;
      default: return <Clock className="w-5 h-5 text-slate-400" />;
    }
  };

  const getStatusColor = (status: QueueItem['status']) => {
    switch (status) {
      case 'completed': return 'text-green-400';
      case 'error': return 'text-red-400';
      case 'processing': return 'text-cyan-400';
      default: return 'text-slate-400';
    }
  };

  return (
    <div className="p-8 h-full flex flex-col animate-fade-in overflow-hidden">
      <div className="mb-8 flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight mb-2">文档转换队列</h1>
          <p className="text-slate-400">批量处理 PDF、HTML 或 TXT 文件，实时监控转换状态。</p>
        </div>
        <div className="flex gap-3">
          {queue.some(i => i.status === 'error') && (
            <button 
              onClick={retryAllFailed}
              className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm border border-white/5 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              全部重试
            </button>
          )}
          {queue.some(i => i.status === 'completed') && (
            <button 
              onClick={clearCompleted}
              className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm border border-white/5 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              清除已完成
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 flex gap-8 min-h-0">
        {/* Left: Upload & List */}
        <div className="flex-1 flex flex-col gap-6 min-h-0">
          
          {/* Upload Zone */}
          <div 
            className={`shrink-0 relative rounded-3xl border-2 border-dashed transition-all duration-300 flex flex-col items-center justify-center p-8
              ${isDragging 
                ? 'border-cyan-400 bg-cyan-400/5 scale-[1.01]' 
                : 'border-white/10 bg-white/[0.02] hover:bg-white/[0.04] hover:border-white/20'
              }
            `}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
          >
            <div className="w-16 h-16 rounded-full bg-slate-800 flex items-center justify-center mb-4 shadow-lg">
              <Upload className="w-8 h-8 text-cyan-400" />
            </div>
            <h3 className="text-lg font-medium text-white mb-1">点击或拖拽上传文件</h3>
            <p className="text-slate-500 text-sm mb-4">支持批量上传</p>
            <label className="relative">
              <input type="file" className="hidden" onChange={handleFileSelect} accept=".pdf,.html,.txt" multiple />
              <span className="px-6 py-2 bg-cyan-500 hover:bg-cyan-400 text-white text-sm font-medium rounded-lg cursor-pointer transition-all shadow-lg shadow-cyan-500/20 active:scale-95 inline-block">
                选择文件
              </span>
            </label>
          </div>

          {/* Queue List */}
          <div className="flex-1 bg-slate-900/50 rounded-2xl border border-white/5 overflow-hidden flex flex-col">
            <div className="p-4 border-b border-white/5 bg-slate-900/80 backdrop-blur-sm sticky top-0 z-10">
               <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider flex items-center gap-2">
                 <RefreshCw className="w-4 h-4" />
                 处理队列 ({queue.length})
               </h3>
            </div>
            
            <div className="overflow-y-auto p-2 space-y-2 custom-scrollbar flex-1">
              {queue.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-slate-500 py-12">
                  <File className="w-12 h-12 mb-4 opacity-20" />
                  <p>队列为空，请上传文件开始处理</p>
                </div>
              ) : (
                queue.map((item) => (
                  <div key={item.id} className="group flex items-center gap-4 p-4 rounded-xl bg-white/5 border border-white/5 hover:bg-white/10 transition-all">
                    {/* Icon Type */}
                    <div className="w-10 h-10 rounded-lg bg-slate-800 flex items-center justify-center shrink-0">
                      <FileType className="w-5 h-5 text-slate-400" />
                    </div>
                    
                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between mb-1">
                        <span className="text-sm font-medium text-white truncate pr-4">{item.file.name}</span>
                        <span className={`text-xs font-medium ${getStatusColor(item.status)} capitalize`}>
                          {item.status === 'error' ? item.errorMessage : item.status}
                        </span>
                      </div>
                      
                      {/* Progress or Meta */}
                      {item.status === 'processing' ? (
                        <div className="h-1.5 w-full bg-slate-700 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-cyan-400 transition-all duration-300" 
                            style={{ width: `${item.progress}%` }}
                          ></div>
                        </div>
                      ) : (
                        <p className="text-xs text-slate-500">{formatFileSize(item.file.size)}</p>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2">
                      {item.status === 'error' && (
                        <button 
                          onClick={() => retryItem(item.id)}
                          className="p-2 text-slate-400 hover:text-cyan-400 hover:bg-cyan-400/10 rounded-lg transition-colors"
                          title="重试"
                        >
                          <RefreshCw className="w-4 h-4" />
                        </button>
                      )}
                      {item.status === 'completed' ? (
                        <div className="p-2">
                           <CheckCircle2 className="w-5 h-5 text-green-500" />
                        </div>
                      ) : (
                        <button 
                          onClick={() => removeItem(item.id)}
                          className="p-2 text-slate-400 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                          title="取消/移除"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Right: Info Panel */}
        <div className="w-80 hidden xl:flex flex-col gap-6 shrink-0">
          <div className="p-6 rounded-2xl bg-white/5 border border-white/5 backdrop-blur-md">
            <h3 className="text-lg font-semibold text-white mb-4">队列状态</h3>
            <div className="space-y-4">
               <div className="flex justify-between items-center">
                  <span className="text-slate-400 text-sm">待处理</span>
                  <span className="text-white font-mono">{queue.filter(i => i.status === 'queued').length}</span>
               </div>
               <div className="flex justify-between items-center">
                  <span className="text-cyan-400 text-sm">处理中</span>
                  <span className="text-cyan-400 font-mono font-bold">{queue.filter(i => i.status === 'processing').length}</span>
               </div>
               <div className="flex justify-between items-center">
                  <span className="text-green-400 text-sm">已完成</span>
                  <span className="text-green-400 font-mono">{queue.filter(i => i.status === 'completed').length}</span>
               </div>
               <div className="flex justify-between items-center">
                  <span className="text-red-400 text-sm">失败</span>
                  <span className="text-red-400 font-mono">{queue.filter(i => i.status === 'error').length}</span>
               </div>
            </div>
            
            <div className="mt-6 pt-6 border-t border-white/10">
               <div className="flex items-center gap-2 mb-2">
                 <Loader2 className="w-4 h-4 text-purple-400 animate-spin" />
                 <span className="text-xs font-semibold text-purple-300">转换引擎活跃</span>
               </div>
               <p className="text-xs text-slate-500">
                 系统采用异步多线程处理队列。大文件可能会导致处理延迟。
               </p>
            </div>
          </div>

           <div className="p-6 rounded-2xl bg-gradient-to-br from-slate-800 to-slate-900 border border-white/5">
              <h3 className="text-sm font-semibold text-white mb-2">支持的格式</h3>
              <div className="flex gap-2 mt-3">
                 <span className="px-2.5 py-1 rounded bg-red-500/20 text-red-300 text-xs border border-red-500/30">PDF</span>
                 <span className="px-2.5 py-1 rounded bg-orange-500/20 text-orange-300 text-xs border border-orange-500/30">HTML</span>
                 <span className="px-2.5 py-1 rounded bg-blue-500/20 text-blue-300 text-xs border border-blue-500/30">TXT</span>
              </div>
           </div>
        </div>
      </div>
    </div>
  );
};

export default Converter;