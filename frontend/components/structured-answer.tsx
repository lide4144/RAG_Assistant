'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeHighlight from 'rehype-highlight';
import { Lightbulb, FileText, AlertTriangle, Quote } from 'lucide-react';

interface StructuredAnswerProps {
  content: string;
}

interface Section {
  type: 'conclusion' | 'evidence' | 'uncertainty' | 'normal';
  title: string;
  content: string;
}

/**
 * 解析结构化回答，识别结论、证据、不确定性边界等章节
 */
function parseStructuredAnswer(content: string): Section[] {
  const sections: Section[] = [];
  
  // 匹配各种可能的章节标题格式
  const patterns = [
    { type: 'conclusion' as const, regex: /(?:^|\n)(?:#{1,3}\s*(?:结论|Conclusion)[：:]?\s*\n?)/i },
    { type: 'evidence' as const, regex: /(?:^|\n)(?:#{1,3}\s*(?:证据|Evidence)[：:]?\s*\n?)/i },
    { type: 'uncertainty' as const, regex: /(?:^|\n)(?:#{1,3}\s*(?:不确定性|Uncertainty|不确定性边界|Uncertainty Boundary)[：:]?\s*\n?)/i },
  ];
  
  // 找到所有章节的位置
  const matches: Array<{ type: 'conclusion' | 'evidence' | 'uncertainty' | 'normal'; index: number; regex: RegExp }> = [];
  
  patterns.forEach(({ type, regex }) => {
    const match = regex.exec(content);
    if (match) {
      matches.push({ type, index: match.index, regex });
    }
  });
  
  // 按位置排序
  matches.sort((a, b) => a.index - b.index);
  
  if (matches.length === 0) {
    // 没有找到结构化章节，直接返回整个内容
    return [{ type: 'normal', title: '', content: content.trim() }];
  }
  
  // 提取前置内容（如果有）
  let currentIndex = 0;
  if (matches[0].index > 0) {
    const preContent = content.slice(0, matches[0].index).trim();
    if (preContent) {
      sections.push({ type: 'normal', title: '', content: preContent });
    }
  }
  
  // 提取各章节内容
  for (let i = 0; i < matches.length; i++) {
    const match = matches[i];
    const nextMatch = matches[i + 1];
    const sectionEnd = nextMatch ? nextMatch.index : content.length;
    
    // 找到标题后的内容开始位置
    const titleMatch = match.regex.exec(content.slice(match.index));
    if (!titleMatch) continue;
    
    const contentStart = match.index + titleMatch[0].length;
    const sectionContent = content.slice(contentStart, sectionEnd).trim();
    
    sections.push({
      type: match.type,
      title: getSectionTitle(match.type),
      content: sectionContent,
    });
    
    currentIndex = sectionEnd;
  }
  
  return sections;
}

function getSectionTitle(type: 'conclusion' | 'evidence' | 'uncertainty' | 'normal'): string {
  switch (type) {
    case 'conclusion':
      return '结论';
    case 'evidence':
      return '证据';
    case 'uncertainty':
      return '不确定性边界';
    default:
      return '';
  }
}

function getSectionIcon(type: 'conclusion' | 'evidence' | 'uncertainty' | 'normal') {
  switch (type) {
    case 'conclusion':
      return Lightbulb;
    case 'evidence':
      return FileText;
    case 'uncertainty':
      return AlertTriangle;
    default:
      return Quote;
  }
}

function getSectionStyles(type: 'conclusion' | 'evidence' | 'uncertainty' | 'normal'): string {
  switch (type) {
    case 'conclusion':
      return 'bg-emerald-50/80 border-emerald-200';
    case 'evidence':
      return 'bg-blue-50/80 border-blue-200';
    case 'uncertainty':
      return 'bg-amber-50/80 border-amber-200';
    default:
      return 'bg-slate-50/80 border-slate-200';
  }
}

function getSectionTitleStyles(type: 'conclusion' | 'evidence' | 'uncertainty' | 'normal'): string {
  switch (type) {
    case 'conclusion':
      return 'text-emerald-800';
    case 'evidence':
      return 'text-blue-800';
    case 'uncertainty':
      return 'text-amber-800';
    default:
      return 'text-slate-800';
  }
}

function getSectionIconStyles(type: 'conclusion' | 'evidence' | 'uncertainty' | 'normal'): string {
  switch (type) {
    case 'conclusion':
      return 'text-emerald-600';
    case 'evidence':
      return 'text-blue-600';
    case 'uncertainty':
      return 'text-amber-600';
    default:
      return 'text-slate-600';
  }
}

export function StructuredAnswer({ content }: StructuredAnswerProps) {
  const sections = React.useMemo(() => parseStructuredAnswer(content), [content]);
  
  // 如果不是结构化回答，使用普通渲染
  if (sections.length === 1 && sections[0].type === 'normal') {
    return (
      <div className="prose prose-sm max-w-none prose-headings:text-slate-900 prose-p:text-slate-700 prose-pre:bg-slate-950 prose-pre:text-slate-100 prose-code:text-slate-900">
        <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex, rehypeHighlight]}>
          {content}
        </ReactMarkdown>
      </div>
    );
  }
  
  // 结构化回答使用卡片式布局
  return (
    <div className="space-y-3">
      {sections.map((section, index) => {
        const Icon = getSectionIcon(section.type);
        
        if (section.type === 'normal') {
          return (
            <div key={index} className="prose prose-sm max-w-none prose-headings:text-slate-900 prose-p:text-slate-700">
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex, rehypeHighlight]}>
                {section.content}
              </ReactMarkdown>
            </div>
          );
        }
        
        return (
          <div
            key={index}
            className={`rounded-[20px] border ${getSectionStyles(section.type)} p-4`}
          >
            <div className="mb-3 flex items-center gap-2">
              <div className={`rounded-full bg-white/80 p-1.5 ${getSectionIconStyles(section.type)}`}>
                <Icon className="h-4 w-4" />
              </div>
              <h3 className={`text-sm font-semibold ${getSectionTitleStyles(section.type)}`}>
                {section.title}
              </h3>
            </div>
            <div className={`prose prose-sm max-w-none prose-p:text-slate-700 ${section.type === 'evidence' ? 'prose-ul:my-2 prose-li:my-0.5' : ''}`}>
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex, rehypeHighlight]}>
                {section.content}
              </ReactMarkdown>
            </div>
          </div>
        );
      })}
    </div>
  );
}
