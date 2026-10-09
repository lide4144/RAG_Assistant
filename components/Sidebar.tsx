import React from 'react';
import { LayoutDashboard, FileInput, Database, MessageSquare, Settings, LogOut, Hexagon } from 'lucide-react';
import { AppView } from '../types';

interface SidebarProps {
  currentView: AppView;
  onChangeView: (view: AppView) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ currentView, onChangeView }) => {
  const menuItems = [
    { id: 'dashboard', label: '系统概览', icon: LayoutDashboard },
    { id: 'converter', label: '文档转换', icon: FileInput },
    { id: 'storage', label: 'RAG 知识库', icon: Database },
    { id: 'query', label: '智能问答', icon: MessageSquare },
  ];

  return (
    <aside className="fixed left-0 top-0 h-full w-72 bg-slate-900/80 backdrop-blur-2xl border-r border-white/5 flex flex-col z-50">
      {/* Logo Area */}
      <div className="p-8 flex items-center gap-3">
        <div className="relative">
          <div className="absolute inset-0 bg-cyan-500 blur-lg opacity-40 rounded-full"></div>
          <Hexagon className="w-8 h-8 text-cyan-400 relative z-10" strokeWidth={2.5} />
        </div>
        <div className="flex flex-col">
          <span className="text-xl font-bold tracking-tight text-white">Nexus<span className="text-cyan-400">Paper</span></span>
          <span className="text-[10px] uppercase tracking-wider text-slate-400 font-medium">资源管理系统 v1.0</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-4 py-6 space-y-2">
        {menuItems.map((item) => {
          const isActive = currentView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onChangeView(item.id as AppView)}
              className={`w-full flex items-center gap-4 px-4 py-3.5 rounded-xl transition-all duration-300 group ${
                isActive 
                  ? 'bg-gradient-to-r from-cyan-500/20 to-blue-500/10 border border-cyan-500/30 text-white shadow-lg shadow-cyan-900/20' 
                  : 'text-slate-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <item.icon 
                className={`w-5 h-5 transition-transform duration-300 ${isActive ? 'text-cyan-400 scale-110' : 'group-hover:text-cyan-200'}`} 
              />
              <span className={`font-medium ${isActive ? 'tracking-wide' : ''}`}>{item.label}</span>
              {isActive && (
                <div className="ml-auto w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.8)]"></div>
              )}
            </button>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 mt-auto">
        <div className="p-4 rounded-xl bg-gradient-to-br from-slate-800/50 to-slate-900/50 border border-white/5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-purple-500 to-indigo-500 flex items-center justify-center text-xs font-bold text-white">
              JD
            </div>
            <div>
              <p className="text-sm font-medium text-white">John Doe</p>
              <p className="text-xs text-slate-400">Research Admin</p>
            </div>
          </div>
          <button 
            onClick={() => onChangeView('settings')}
            className={`w-full flex items-center justify-center gap-2 text-xs font-medium transition-colors py-2 border-t border-white/5 mt-2 
              ${currentView === 'settings' ? 'text-cyan-400 bg-white/5 rounded-lg' : 'text-slate-400 hover:text-white'}`}
          >
            <Settings className="w-3.5 h-3.5" />
            设置
          </button>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;