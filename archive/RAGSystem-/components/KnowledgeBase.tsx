import React from 'react';
import { MOCK_DOCUMENTS } from '../constants';
import { Search, Filter, MoreHorizontal, Database, Calendar, Tag } from 'lucide-react';
import { FileType, PaperDocument } from '../types';

const DocumentCard: React.FC<{ doc: PaperDocument }> = ({ doc }) => {
  const getBadgeColor = (type: FileType) => {
    switch(type) {
      case FileType.PDF: return 'bg-red-500/20 text-red-300 border-red-500/30';
      case FileType.HTML: return 'bg-orange-500/20 text-orange-300 border-orange-500/30';
      case FileType.TXT: return 'bg-blue-500/20 text-blue-300 border-blue-500/30';
      default: return 'bg-slate-500/20 text-slate-300';
    }
  };

  return (
    <div className="group relative p-5 rounded-2xl bg-slate-800/40 border border-white/5 hover:bg-slate-800/60 hover:border-cyan-500/30 transition-all duration-300 hover:-translate-y-1">
      <div className="flex justify-between items-start mb-4">
        <div className={`px-2.5 py-1 rounded-md text-[10px] font-bold border ${getBadgeColor(doc.type)}`}>
          {doc.type}
        </div>
        <button className="text-slate-500 hover:text-white transition-colors">
          <MoreHorizontal className="w-5 h-5" />
        </button>
      </div>

      <h3 className="text-lg font-semibold text-white mb-2 line-clamp-2 min-h-[3.5rem] group-hover:text-cyan-400 transition-colors">
        {doc.title}
      </h3>

      <div className="flex flex-wrap gap-2 mb-4">
        {doc.metadata.tags.map((tag, i) => (
          <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-slate-400 border border-white/5">
            #{tag}
          </span>
        ))}
      </div>

      <div className="flex items-center justify-between pt-4 border-t border-white/5 text-xs text-slate-500">
        <div className="flex items-center gap-1.5">
          <Calendar className="w-3.5 h-3.5" />
          <span>{doc.metadata.processedAt.split(' ')[0]}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Database className="w-3.5 h-3.5 text-cyan-500/70" />
          <span>{doc.vectorCount} vectors</span>
        </div>
      </div>
      
      {/* Active Indicator Line */}
      <div className="absolute bottom-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-cyan-500 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
    </div>
  );
};

const KnowledgeBase: React.FC = () => {
  return (
    <div className="p-8 animate-fade-in space-y-8">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight mb-2">知识库存储</h1>
          <p className="text-slate-400">管理 ChromaDB 中的向量数据。总计 1,248 篇文档。</p>
        </div>
        
        <div className="flex items-center gap-3">
          <div className="relative group">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 group-focus-within:text-cyan-400 transition-colors" />
            <input 
              type="text" 
              placeholder="搜索文档..." 
              className="pl-10 pr-4 py-2.5 bg-slate-900/50 border border-white/10 rounded-xl text-sm text-white focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 w-64 transition-all"
            />
          </div>
          <button className="p-2.5 bg-white/5 border border-white/10 rounded-xl hover:bg-white/10 hover:text-white text-slate-400 transition-colors">
            <Filter className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {MOCK_DOCUMENTS.map((doc) => (
          <DocumentCard key={doc.id} doc={doc} />
        ))}
        {MOCK_DOCUMENTS.map((doc) => (
           // Duplicate mock data to fill grid for demo
          <DocumentCard key={`${doc.id}-copy`} doc={{...doc, id: `${doc.id}-copy`}} />
        ))}
      </div>
    </div>
  );
};

export default KnowledgeBase;