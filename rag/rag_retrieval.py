"""
能源审计RAG知识检索工具
基于Qdrant向量数据库的RAG系统
"""

import os
import sys
from typing import Dict, List, Optional
import json

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

try:
    from llamaindex_qdrant_qa import (
        init_models, load_index, make_query_engine, 
        DEFAULT_COLLECTION, QDRANT_URL
    )
    RAG_SYSTEM_AVAILABLE = True
except ImportError:
    RAG_SYSTEM_AVAILABLE = False
    print("警告: RAG系统不可用，请检查llamaindex_qdrant_qa.py")


class RAGKnowledgeRetrieval:
    """RAG知识检索器"""
    
    def __init__(self, collection_name: str = None):
        """
        初始化RAG知识检索器
        
        Args:
            collection_name: Qdrant集合名称
        """
        self.collection_name = collection_name
        if not self.collection_name:
            try:
                from rag.config import energy_audit_collection

                self.collection_name = energy_audit_collection()
            except Exception:
                self.collection_name = DEFAULT_COLLECTION
        self.index = None
        self.query_engine = None
        self.initialized = False
        
    def initialize(self):
        """初始化RAG系统"""
        if not RAG_SYSTEM_AVAILABLE:
            raise Exception("RAG系统不可用")
        
        try:
            # 初始化模型
            init_models()
            
            # 加载索引
            self.index = load_index(self.collection_name)
            
            # 创建查询引擎
            self.query_engine = make_query_engine(
                self.index, 
                top_k=5, 
                response_mode="compact"
            )
            
            self.initialized = True
            print(f"RAG系统初始化成功，使用集合: {self.collection_name}")
            
        except Exception as e:
            raise Exception(f"RAG系统初始化失败: {str(e)}")
    
    def search(self, query: str, top_k: int = 5) -> Dict:
        """
        语义检索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            检索结果字典
        """
        if not self.initialized:
            self.initialize()
        
        try:
            # 执行查询
            response = self.query_engine.query(query)
            
            # 构建结果
            results = {
                'query': query,
                'answer': str(response),
                'sources': [],
                'confidence': 0.0
            }
            
            # 提取来源信息
            if hasattr(response, 'source_nodes'):
                for i, node in enumerate(response.source_nodes[:top_k], 1):
                    source_info = {
                        'index': i,
                        'content': node.node.text[:500] + '...' if len(node.node.text) > 500 else node.node.text,
                        'score': node.score if hasattr(node, 'score') else 0.0,
                        'metadata': node.node.metadata if hasattr(node.node, 'metadata') else {}
                    }
                    results['sources'].append(source_info)
                
                # 计算平均置信度
                if results['sources']:
                    results['confidence'] = sum(s['score'] for s in results['sources']) / len(results['sources'])
            
            return results
            
        except Exception as e:
            raise Exception(f"检索失败: {str(e)}")
    
    def search_standards(self, audit_type: str, topic: str) -> Dict:
        """
        搜索相关标准规范
        
        Args:
            audit_type: 审计类型 (公共机构、公共建筑、工业企业)
            topic: 主题
            
        Returns:
            相关标准信息
        """
        query = f"{audit_type}能源审计{topic}相关标准规范"
        return self.search(query)
    
    def search_best_practices(self, audit_type: str, system_type: str) -> Dict:
        """
        搜索最佳实践
        
        Args:
            audit_type: 审计类型
            system_type: 系统类型 (空调、照明、供暖等)
            
        Returns:
            最佳实践信息
        """
        query = f"{audit_type}{system_type}节能最佳实践"
        return self.search(query)
    
    def search_calculation_methods(self, indicator: str) -> Dict:
        """
        搜索计算方法
        
        Args:
            indicator: 指标名称
            
        Returns:
            计算方法信息
        """
        query = f"{indicator}计算方法公式"
        return self.search(query)
    
    def search_case_studies(self, audit_type: str, building_type: str = None) -> Dict:
        """
        搜索案例研究
        
        Args:
            audit_type: 审计类型
            building_type: 建筑类型
            
        Returns:
            案例研究信息
        """
        query = f"{audit_type}能源审计案例"
        if building_type:
            query += f" {building_type}"
        return self.search(query)
    
    def search_energy_saving_measures(self, system_type: str) -> Dict:
        """
        搜索节能措施
        
        Args:
            system_type: 系统类型
            
        Returns:
            节能措施信息
        """
        query = f"{system_type}节能改造措施"
        return self.search(query)
    
    def get_audit_requirements(self, audit_type: str) -> Dict:
        """
        获取审计要求
        
        Args:
            audit_type: 审计类型
            
        Returns:
            审计要求信息
        """
        query = f"{audit_type}能源审计要求和流程"
        return self.search(query)
    
    def export_results(self, results: Dict, output_format: str = 'json') -> str:
        """
        导出检索结果
        
        Args:
            results: 检索结果
            output_format: 输出格式 ('json', 'text', 'markdown')
            
        Returns:
            格式化后的结果
        """
        if output_format == 'json':
            return json.dumps(results, ensure_ascii=False, indent=2)
        elif output_format == 'text':
            text = f"查询: {results['query']}\n\n"
            text += f"答案:\n{results['answer']}\n\n"
            text += f"来源:\n"
            for source in results['sources']:
                text += f"  [{source['index']}] {source['content']}\n"
                text += f"      置信度: {source['score']:.2f}\n\n"
            return text
        elif output_format == 'markdown':
            md = f"# 检索结果\n\n"
            md += f"## 查询\n{results['query']}\n\n"
            md += f"## 答案\n{results['answer']}\n\n"
            md += f"## 来源\n"
            for source in results['sources']:
                md += f"### 来源 {source['index']}\n"
                md += f"{source['content']}\n\n"
                md += f"**置信度:** {source['score']:.2f}\n\n"
            return md
        else:
            raise ValueError(f"不支持的输出格式: {output_format}")


# 使用示例
if __name__ == "__main__":
    # 示例：搜索公共机构能源审计相关标准
    rag = RAGKnowledgeRetrieval()
    
    try:
        # 初始化
        rag.initialize()
        
        # 搜索相关标准
        results = rag.search_standards("公共机构", "能耗指标")
        print("相关标准:")
        print(rag.export_results(results, 'text'))
        
        # 搜索计算方法
        results = rag.search_calculation_methods("人均综合能耗")
        print("\n计算方法:")
        print(rag.export_results(results, 'text'))
        
        # 搜索最佳实践
        results = rag.search_best_practices("公共机构", "空调系统")
        print("\n最佳实践:")
        print(rag.export_results(results, 'text'))
        
    except Exception as e:
        print(f"错误: {str(e)}")
