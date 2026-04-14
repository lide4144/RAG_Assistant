import { LibraryShell } from '../../components/library-shell';

export const metadata = {
  title: '知识库管理 - RAG GPT',
  description: '管理已导入的论文，支持查看、删除、重建和批量操作',
};

export default function LibraryPage() {
  return <LibraryShell />;
}
