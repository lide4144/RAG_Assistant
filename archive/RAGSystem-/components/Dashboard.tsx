import React from 'react';
import { SYSTEM_STATS } from '../constants';
import * as Icons from 'lucide-react';
import { ArrowRight, Activity, Database, FileText, Cpu } from 'lucide-react';

const StatCard: React.FC<{ label: string; value: string; change: string; icon: string; delay: number }> = ({ label, value, change, icon, delay }) => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const LucideIcon = (Icons as any)[icon];
  
  return (
    <div 
      className="relative p-6 rounded-2xl bg-white/5 backdrop-blur-md border border-white/10 overflow-hidden group hover:bg-white/10 transition-all duration-300 hover:transform hover:-translate-y-1"
      style={{ animation: `fadeInUp 0.6s ease-out ${delay}s backwards` }}
    >
      <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-cyan-500/10 to-transparent rounded-full blur-2xl -mr-16 -mt-16 group-hover:from-cyan-500/20 transition-all duration-500"></div>
      
      <div className="flex justify-between items-start mb-4">
        <div className="p-3 rounded-lg bg-slate-900/50 border border-white/5 text-cyan-400 group-hover:text-white group-hover:bg-cyan-500/20 transition-all duration-300">
          <LucideIcon className="w-6 h-6" />
        </div>
        <span className={`text-xs font-medium px-2 py-1 rounded-full ${change.startsWith('+') ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
          {change}
        </span>
      </div>
      <h3 className="text-3xl font-bold text-white mb-1 tracking-tight">{value}</h3>
      <p className="text-sm text-slate-400 font-medium">{label}</p>
    </div>
  );
};

const ArchitectureNode: React.FC<{ title: string; subtitle: string; icon: React.ReactNode; color: string }> = ({ title, subtitle, icon, color }) => (
  <div className={`flex flex-col items-center p-6 rounded-2xl bg-slate-900/60 backdrop-blur border border-${color}-500/30 shadow-[0_0_30px_rgba(0,0,0,0.3)] w-48 relative group hover:scale-105 transition-all duration-300 z-10`}>
    <div className={`absolute inset-0 bg-${color}-500/5 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300`}></div>
    <div className={`w-12 h-12 rounded-xl bg-${color}-500/20 text-${color}-400 flex items-center justify-center mb-4 shadow-[0_0_15px_rgba(var(--${color}-500-rgb),0.3)]`}>
      {icon}
    </div>
    <h4 className="text-white font-semibold text-sm mb-1">{title}</h4>
    <p className="text-xs text-slate-400 text-center">{subtitle}</p>
    
    {/* Connection Dot */}
    <div className="absolute -right-3 top-1/2 w-2 h-2 bg-slate-600 rounded-full z-20 hidden md:block"></div>
  </div>
);

const Dashboard: React.FC = () => {
  return (
    <div className="p-8 space-y-8 animate-fade-in">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-bold text-white tracking-tight">系统概览</h1>
        <p className="text-slate-400">实时监控论文处理流水线与知识库状态。</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {SYSTEM_STATS.map((stat, idx) => (
          <StatCard key={idx} {...stat} delay={idx * 0.1} />
        ))}
      </div>

      {/* Architecture Visualization */}
      <div className="rounded-3xl bg-white/5 border border-white/5 p-8 relative overflow-hidden backdrop-blur-sm">
        <div className="absolute inset-0 bg-grid-white/[0.02] bg-[size:32px_32px]"></div>
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-slate-900/90 pointer-events-none"></div>
        
        <div className="relative z-10 mb-8 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Activity className="w-5 h-5 text-cyan-400" />
            系统实时数据流
          </h2>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
            <span className="text-xs text-green-400 font-medium">系统正常运行</span>
          </div>
        </div>

        <div className="relative flex flex-col md:flex-row items-center justify-between gap-8 py-10 px-4 md:px-12">
          {/* Connecting Lines */}
          <div className="absolute top-1/2 left-0 w-full h-0.5 bg-gradient-to-r from-transparent via-slate-700 to-transparent -translate-y-1/2 hidden md:block z-0"></div>
          
          <ArchitectureNode 
            title="输入源" 
            subtitle="PDF / HTML / TXT"
            icon={<FileText className="w-6 h-6" />}
            color="blue"
          />
          
          <div className="text-slate-600 animate-pulse hidden md:block relative z-10 bg-slate-900 px-2 rounded-full">
            <ArrowRight className="w-5 h-5" />
          </div>

          <ArchitectureNode 
            title="文档转换" 
            subtitle="Markdown 结构化"
            icon={<Cpu className="w-6 h-6" />}
            color="purple"
          />

          <div className="text-slate-600 animate-pulse hidden md:block relative z-10 bg-slate-900 px-2 rounded-full">
            <ArrowRight className="w-5 h-5" />
          </div>

          <ArchitectureNode 
            title="向量存储" 
            subtitle="ChromaDB Embedding"
            icon={<Database className="w-6 h-6" />}
            color="amber"
          />
          
           <div className="text-slate-600 animate-pulse hidden md:block relative z-10 bg-slate-900 px-2 rounded-full">
            <ArrowRight className="w-5 h-5" />
          </div>

          <ArchitectureNode 
            title="RAG 查询" 
            subtitle="LLM 智能问答"
            icon={<Activity className="w-6 h-6" />}
            color="cyan"
          />
        </div>
      </div>
    </div>
  );
};

export default Dashboard;