"""
PDF 文档导入知识图谱工具
将 PDF 文档提取、分块、向量化并存储到 Qdrant (gRPC)
"""

import os
import sys
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from qdrant_client import QdrantClient
from qdrant_client.models import PointIdsList, PointStruct

from rag.config import qdrant_client_kwargs, qdrant_grpc_port

KNOWLEDGE_COLLECTION = "knowledge_segment"
VECTOR_SIZE = 1024


class PDFToKnowledgeGraph:
    """PDF 文档导入知识图谱"""

    def __init__(
        self, qdrant_host: str | None = None, qdrant_port: int | None = None
    ):
        if qdrant_host:
            self._client = QdrantClient(
                host=qdrant_host, port=int(qdrant_port or qdrant_grpc_port()), prefer_grpc=True, timeout=60,
                check_compatibility=False,
            )
        else:
            self._client = QdrantClient(**qdrant_client_kwargs(timeout=60))
        self.collection_name = KNOWLEDGE_COLLECTION

    def extract_text_pymupdf(
        self, pdf_path: str, pages: Optional[str] = None
    ) -> Optional[Dict]:
        """使用 pymupdf 提取 PDF 文本"""
        try:
            import pymupdf
        except ImportError:
            print("❌ 请先安装 pymupdf: pip install pymupdf pymupdf4llm")
            return None

        if not os.path.exists(pdf_path):
            print(f"❌ 文件不存在: {pdf_path}")
            return None

        print(f"📄 正在提取 PDF: {pdf_path}")

        doc = pymupdf.open(pdf_path)
        total_pages = len(doc)

        page_range = None
        if pages:
            if "-" in pages:
                start, end = pages.split("-")
                page_range = (int(start), int(end))
            else:
                page_range = (int(pages), int(pages))

        pages_text = []
        start_page = page_range[0] if page_range else 0
        end_page = page_range[1] if page_range else total_pages - 1

        for i in range(start_page, min(end_page + 1, total_pages)):
            page = doc[i]
            text = page.get_text()
            if text.strip():
                pages_text.append({"page_number": i + 1, "content": text.strip()})

        doc.close()
        print(f"✅ 提取完成: {len(pages_text)} 页文本")

        return {
            "pdf_path": pdf_path,
            "total_pages": total_pages,
            "extracted_pages": len(pages_text),
            "pages": pages_text,
        }

    def extract_text_marker(self, pdf_path: str) -> Optional[Dict]:
        """使用 marker-pdf 提取 PDF 文本（支持 OCR）"""
        try:
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict
        except ImportError:
            print("❌ 请先安装 marker-pdf: pip install marker-pdf")
            print("   注意: marker-pdf 需要约 3-5GB 磁盘空间")
            return None

        if not os.path.exists(pdf_path):
            print(f"❌ 文件不存在: {pdf_path}")
            return None

        print(f"📄 正在使用 marker-pdf 提取: {pdf_path}")
        print("   ⏳ 首次运行可能需要下载模型...")

        try:
            converter = PdfConverter(artifact_dict=create_model_dict())
            rendered = converter(pdf_path)
            markdown_text = rendered.markdown
            print(f"✅ 提取完成: {len(markdown_text)} 字符")
            return {
                "pdf_path": pdf_path,
                "content": markdown_text,
                "length": len(markdown_text),
            }
        except Exception as e:
            print(f"❌ marker-pdf 提取失败: {e}")
            return None

    @staticmethod
    def split_text_into_chunks(
        text: str, chunk_size: int = 500, overlap: int = 50
    ) -> List[str]:
        """将文本分块"""
        if not text:
            return []

        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = start + chunk_size
            if end < text_length:
                for sep in ["\n\n", "\n", "。", "！", "？", ".", "!", "?"]:
                    last_sep = text[start:end].rfind(sep)
                    if last_sep > chunk_size * 0.3:
                        end = start + last_sep + len(sep)
                        break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start = end - overlap

        return chunks

    def prepare_document_chunks(
        self,
        pdf_path: str,
        extraction_method: str = "pymupdf",
        chunk_size: int = 500,
        pages: Optional[str] = None,
    ) -> Optional[Dict]:
        """准备文档分块"""
        if extraction_method == "marker":
            result = self.extract_text_marker(pdf_path)
            if not result:
                return None
            full_text = result["content"]
            pages_info = [{"page_number": 1, "content": full_text}]
        else:
            result = self.extract_text_pymupdf(pdf_path, pages)
            if not result:
                return None
            pages_info = result["pages"]
            full_text = "\n\n".join([p["content"] for p in pages_info])

        document_id = str(uuid.uuid4())
        knowledge_id = str(uuid.uuid4())

        all_chunks = []
        chunk_index = 0
        for page_info in pages_info:
            page_text = page_info["content"]
            page_chunks = self.split_text_into_chunks(page_text, chunk_size)
            for chunk_text in page_chunks:
                segment_id = str(uuid.uuid4())
                all_chunks.append({
                    "id": segment_id,
                    "chunk_index": chunk_index,
                    "content": chunk_text,
                    "page_number": page_info["page_number"],
                    "document_id": document_id,
                    "knowledge_id": knowledge_id,
                    "source": os.path.basename(pdf_path),
                })
                chunk_index += 1

        print(f"✅ 分块完成: {len(all_chunks)} 个分块")

        return {
            "document_id": document_id,
            "knowledge_id": knowledge_id,
            "pdf_path": pdf_path,
            "total_chunks": len(all_chunks),
            "chunks": all_chunks,
            "full_text_length": len(full_text),
        }

    def upload_to_qdrant(
        self, document_data: Dict, batch_size: int = 10
    ) -> bool:
        """上传分块到 Qdrant"""
        chunks = document_data.get("chunks")
        if not chunks:
            print("❌ 没有数据可上传")
            return False

        total_chunks = len(chunks)
        document_id = document_data["document_id"]
        knowledge_id = document_data["knowledge_id"]

        print(f"📤 开始上传 {total_chunks} 个分块到 Qdrant...")

        success_count = 0
        for i in range(0, total_chunks, batch_size):
            batch = chunks[i : i + batch_size]

            points = []
            for chunk in batch:
                points.append(
                    PointStruct(
                        id=chunk["id"],
                        vector=[0.0] * VECTOR_SIZE,  # 占位向量
                        payload={
                            "doc_content": chunk["content"],
                            "documentId": chunk["document_id"],
                            "knowledgeId": chunk["knowledge_id"],
                            "segmentId": chunk["id"],
                            "parent_document_id": document_id,
                            "chunk_index": chunk["chunk_index"],
                            "total_chunks": total_chunks,
                            "page_number": chunk.get("page_number", 0),
                            "source": chunk.get("source", ""),
                            "uploaded_at": datetime.now().isoformat(),
                        },
                    )
                )

            self._client.upsert(
                collection_name=self.collection_name, points=points
            )
            success_count += len(batch)
            print(f"  ✅ 已上传 {success_count}/{total_chunks} 个分块")

        print(f"✅ 上传完成: {success_count} 个分块")
        return True

    def process_pdf(
        self,
        pdf_path: str,
        extraction_method: str = "pymupdf",
        chunk_size: int = 500,
        pages: Optional[str] = None,
    ) -> Dict:
        """完整处理流程"""
        print("=" * 60)
        print("PDF 文档导入知识图谱")
        print("=" * 60)
        print()

        print("[1] 提取和分块文档...")
        document_data = self.prepare_document_chunks(
            pdf_path, extraction_method, chunk_size, pages
        )

        if not document_data:
            return {"success": False, "error": "文档处理失败"}

        print("\n[2] 上传到 Qdrant...")
        upload_success = self.upload_to_qdrant(document_data)

        if not upload_success:
            return {"success": False, "error": "上传失败"}

        result = {
            "success": True,
            "document_id": document_data["document_id"],
            "knowledge_id": document_data["knowledge_id"],
            "pdf_path": pdf_path,
            "total_chunks": document_data["total_chunks"],
            "full_text_length": document_data["full_text_length"],
            "collection": self.collection_name,
        }

        print("\n" + "=" * 60)
        print("✅ 处理完成!")
        print("=" * 60)
        print(f"文档 ID: {result['document_id']}")
        print(f"分块数量: {result['total_chunks']}")
        print(f"文本长度: {result['full_text_length']} 字符")
        print(f"存储集合: {result['collection']}")
        print()

        return result

    def _scroll_all(self) -> List:
        """Scroll all points from the collection."""
        all_points = []
        offset = None
        while True:
            points, next_offset = self._client.scroll(
                collection_name=self.collection_name,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            all_points.extend(points)
            if next_offset is None or not points:
                break
            offset = next_offset
        return all_points

    def list_documents(self) -> List[Dict]:
        """列出已导入的文档"""
        all_points = self._scroll_all()

        documents = {}
        for p in all_points:
            payload = p.payload or {}
            doc_id = payload.get("documentId")
            if doc_id and doc_id not in documents:
                documents[doc_id] = {
                    "document_id": doc_id,
                    "knowledge_id": payload.get("knowledgeId"),
                    "source": payload.get("source", "Unknown"),
                    "total_chunks": payload.get("total_chunks", 0),
                    "uploaded_at": payload.get("uploaded_at", ""),
                }

        return list(documents.values())

    def search_document(self, keyword: str, limit: int = 10) -> List[Dict]:
        """搜索文档内容"""
        all_points = self._scroll_all()

        matched_chunks = []
        for p in all_points:
            payload = p.payload or {}
            content = payload.get("doc_content", "")

            if keyword.lower() in content.lower():
                matched_chunks.append({
                    "id": p.id,
                    "content": content[:200] + "..." if len(content) > 200 else content,
                    "source": payload.get("source", ""),
                    "page_number": payload.get("page_number", 0),
                    "chunk_index": payload.get("chunk_index", 0),
                })

        return matched_chunks[:limit]

    def delete_document(self, document_id: str) -> bool:
        """删除文档的所有分块"""
        all_points = self._scroll_all()

        chunk_ids = [
            p.id
            for p in all_points
            if (p.payload or {}).get("documentId") == document_id
        ]

        if not chunk_ids:
            print(f"❌ 未找到文档: {document_id}")
            return False

        self._client.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(points=chunk_ids),
        )
        print(f"✅ 已删除文档: {document_id} ({len(chunk_ids)} 个分块)")
        return True


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="PDF 文档导入知识图谱")
    parser.add_argument(
        "action",
        choices=["import", "list", "search", "delete"],
        help="操作类型",
    )
    parser.add_argument("--pdf", help="PDF 文件路径")
    parser.add_argument(
        "--method", choices=["pymupdf", "marker"], default="pymupdf",
        help="提取方法",
    )
    parser.add_argument("--chunk-size", type=int, default=500, help="分块大小")
    parser.add_argument("--pages", help="页码范围 (如: 0-10)")
    parser.add_argument("--keyword", help="搜索关键词")
    parser.add_argument("--document-id", help="文档 ID")
    parser.add_argument("--limit", type=int, default=10, help="搜索结果数量")

    args = parser.parse_args()
    tool = PDFToKnowledgeGraph()

    if args.action == "import":
        if not args.pdf:
            print("❌ 请指定 PDF 文件路径: --pdf <path>")
            return
        result = tool.process_pdf(
            args.pdf,
            extraction_method=args.method,
            chunk_size=args.chunk_size,
            pages=args.pages,
        )
        if result["success"]:
            print(f"\n文档 ID: {result['document_id']}")
            print("使用以下命令查看文档:")
            print("  python pdf_to_knowledge_graph.py list")
            print("  python pdf_to_knowledge_graph.py search --keyword <关键词>")

    elif args.action == "list":
        documents = tool.list_documents()
        print(f"\n已导入的文档 ({len(documents)} 个):")
        print("-" * 60)
        for doc in documents:
            print(f"文档 ID: {doc['document_id']}")
            print(f"来源: {doc['source']}")
            print(f"分块数: {doc['total_chunks']}")
            print(f"上传时间: {doc['uploaded_at']}")
            print("-" * 60)

    elif args.action == "search":
        if not args.keyword:
            print("❌ 请指定搜索关键词: --keyword <keyword>")
            return
        results = tool.search_document(args.keyword, args.limit)
        print(f"\n搜索结果 ({len(results)} 条):")
        print("-" * 60)
        for r in results:
            print(f"来源: {r['source']}, 页码: {r['page_number']}")
            print(f"内容: {r['content']}")
            print("-" * 60)

    elif args.action == "delete":
        if not args.document_id:
            print("❌ 请指定文档 ID: --document-id <id>")
            return
        tool.delete_document(args.document_id)


if __name__ == "__main__":
    main()
