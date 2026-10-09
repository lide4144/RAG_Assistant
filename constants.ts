import { PaperDocument, FileType, ChatMessage } from './types';

export const MOCK_DOCUMENTS: PaperDocument[] = [
  {
    id: '1',
    title: 'Attention Is All You Need',
    type: FileType.PDF,
    size: '2.4 MB',
    status: 'indexed',
    vectorCount: 154,
    metadata: {
      tags: ['Transformer', 'NLP', 'Deep Learning'],
      processedAt: '2023-10-24 14:30'
    }
  },
  {
    id: '2',
    title: 'RAG Architecture Overview',
    type: FileType.HTML,
    size: '156 KB',
    status: 'indexed',
    vectorCount: 45,
    metadata: {
      tags: ['Architecture', 'Retrieval', 'System Design'],
      processedAt: '2023-10-25 09:15'
    }
  },
  {
    id: '3',
    title: 'ChromaDB Optimization Techniques',
    type: FileType.TXT,
    size: '45 KB',
    status: 'processing',
    vectorCount: 0,
    metadata: {
      tags: ['Database', 'Vector', 'Optimization'],
      processedAt: '2023-10-26 11:00'
    }
  }
];

export const INITIAL_CHAT_HISTORY: ChatMessage[] = [
  {
    id: 'msg_1',
    role: 'assistant',
    content: '您好！我是您的智能论文助手。我可以帮助您查询知识库中的任何论文内容。请问有什么可以帮您？',
    timestamp: Date.now()
  }
];

export const SYSTEM_STATS = [
  { label: '已索引文档', value: '1,248', change: '+12%', icon: 'FileText' },
  { label: '向量切片数', value: '84,392', change: '+5%', icon: 'Database' },
  { label: '平均查询耗时', value: '145ms', change: '-8%', icon: 'Zap' },
  { label: 'Token 使用量', value: '4.2M', change: '+24%', icon: 'Cpu' }
];