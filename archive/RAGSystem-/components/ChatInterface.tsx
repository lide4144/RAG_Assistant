import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Sparkles, BookOpen } from 'lucide-react';
import { ChatMessage } from '../types';
import { INITIAL_CHAT_HISTORY } from '../constants';

const ChatInterface: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_CHAT_HISTORY);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  const handleSend = () => {
    if (!input.trim()) return;

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: Date.now()
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsTyping(true);

    // Simulate RAG Latency & Streaming
    setTimeout(() => {
      const aiMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: '根据检索到的文档《Attention Is All You Need》，Transformer 模型完全基于注意力机制，摒弃了循环和卷积。其核心在于 Multi-Head Attention，允许模型同时关注来自不同位置的表示子空间的信息。',
        timestamp: Date.now(),
        sources: ['1'],
        confidence: 0.92
      };
      setMessages(prev => [...prev, aiMsg]);
      setIsTyping(false);
    }, 1500);
  };

  return (
    <div className="h-full flex flex-col animate-fade-in relative overflow-hidden">
      {/* Header */}
      <div className="p-6 border-b border-white/5 bg-slate-900/50 backdrop-blur-md z-10 flex justify-between items-center">
        <div>
           <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-cyan-400" />
            智能问答
          </h1>
           <p className="text-sm text-slate-400">模型: GPT-4-Turbo (RAG Context Enabled)</p>
        </div>
        <div className="px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-xs font-mono text-cyan-400">
          Connected
        </div>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
            {/* Avatar */}
            <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 border 
              ${msg.role === 'assistant' 
                ? 'bg-cyan-500/20 border-cyan-500/30 text-cyan-400' 
                : 'bg-slate-700/50 border-white/10 text-slate-300'
              }`}>
              {msg.role === 'assistant' ? <Bot className="w-5 h-5" /> : <User className="w-5 h-5" />}
            </div>

            {/* Bubble */}
            <div className={`flex flex-col max-w-[80%] ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
              <div className={`p-4 rounded-2xl text-sm leading-relaxed shadow-lg backdrop-blur-sm
                ${msg.role === 'assistant' 
                  ? 'bg-slate-800/80 border border-white/5 text-slate-100 rounded-tl-none' 
                  : 'bg-gradient-to-br from-cyan-600 to-blue-600 text-white rounded-tr-none'
                }`}>
                {msg.content}
              </div>
              
              {/* Sources Footnote for AI */}
              {msg.role === 'assistant' && msg.sources && (
                <div className="mt-2 flex gap-2">
                  {msg.sources.map(srcId => (
                    <div key={srcId} className="flex items-center gap-1 px-2 py-1 bg-white/5 rounded-md border border-white/5 text-[10px] text-cyan-300 cursor-pointer hover:bg-white/10 transition-colors">
                      <BookOpen className="w-3 h-3" />
                      <span>Source #{srcId}</span>
                    </div>
                  ))}
                  {msg.confidence && (
                    <span className="text-[10px] text-slate-500 self-center ml-2">Confidence: {(msg.confidence * 100).toFixed(0)}%</span>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        
        {isTyping && (
          <div className="flex gap-4">
            <div className="w-10 h-10 rounded-full bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
              <Bot className="w-5 h-5" />
            </div>
            <div className="p-4 rounded-2xl rounded-tl-none bg-slate-800/80 border border-white/5 flex items-center gap-1">
              <span className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce"></span>
              <span className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></span>
              <span className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-6 bg-slate-900/80 backdrop-blur-xl border-t border-white/5">
        <div className="relative max-w-4xl mx-auto">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="询问有关文档的问题..."
            className="w-full pl-6 pr-14 py-4 bg-slate-800/50 border border-white/10 rounded-2xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30 focus:border-cyan-500/50 transition-all shadow-xl"
          />
          <button 
            onClick={handleSend}
            disabled={!input.trim()}
            className="absolute right-3 top-1/2 -translate-y-1/2 p-2.5 bg-gradient-to-r from-cyan-500 to-blue-500 rounded-xl text-white shadow-lg shadow-cyan-500/20 hover:shadow-cyan-500/40 hover:scale-105 active:scale-95 disabled:opacity-50 disabled:scale-100 transition-all"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
        <p className="text-center text-xs text-slate-600 mt-3">NexusPaper AI 可能会产生不准确的信息，请核对重要事实。</p>
      </div>
    </div>
  );
};

export default ChatInterface;