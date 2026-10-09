import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import Dashboard from './components/Dashboard';
import Converter from './components/Converter';
import KnowledgeBase from './components/KnowledgeBase';
import ChatInterface from './components/ChatInterface';
import Settings from './components/Settings';
import { AppView } from './types';

const App: React.FC = () => {
  const [currentView, setCurrentView] = useState<AppView>('dashboard');

  const renderView = () => {
    switch (currentView) {
      case 'dashboard':
        return <Dashboard />;
      case 'converter':
        return <Converter />;
      case 'storage':
        return <KnowledgeBase />;
      case 'query':
        return <ChatInterface />;
      case 'settings':
        return <Settings />;
      default:
        return <Dashboard />;
    }
  };

  return (
    <div className="flex h-screen w-full bg-[#0f172a] text-slate-200 overflow-hidden font-sans selection:bg-cyan-500/30">
      {/* Ambient Background Effects */}
      <div className="fixed top-[-10%] left-[-10%] w-[50%] h-[50%] bg-purple-900/20 rounded-full blur-[120px] pointer-events-none blob"></div>
      <div className="fixed bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-cyan-900/20 rounded-full blur-[120px] pointer-events-none blob" style={{ animationDelay: '-5s' }}></div>

      <Sidebar currentView={currentView} onChangeView={setCurrentView} />

      <main className="flex-1 ml-72 h-full relative z-10 overflow-hidden">
         {/* Top glass gradient overlay for depth */}
         <div className="absolute top-0 left-0 right-0 h-24 bg-gradient-to-b from-slate-900/50 to-transparent pointer-events-none z-20"></div>
         
         <div className="h-full overflow-y-auto custom-scrollbar">
           {renderView()}
         </div>
      </main>
    </div>
  );
};

export default App;