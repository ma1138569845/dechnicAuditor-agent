"""
能源审计工具包
提供能源审计相关的数据处理、查询、检索和报告生成功能
"""

import os

__version__ = '2.0.0'
__author__ = '马天远'

__all__ = [
    'ExcelDataProcessor',
    'PgDataQuery',
    'RAGKnowledgeRetrieval',
    'ReportGenerator'
]


def __getattr__(name: str):
    """延迟导入重依赖模块，避免无条件加载 pandas / qdrant 等。"""
    if name == "ExcelDataProcessor":
        from .excel_processor import ExcelDataProcessor
        return ExcelDataProcessor
    if name == "PgDataQuery":
        from .pg_query import PgDataQuery
        return PgDataQuery
    if name == "RAGKnowledgeRetrieval":
        from rag.rag_retrieval import RAGKnowledgeRetrieval
        return RAGKnowledgeRetrieval
    if name == "ReportGenerator":
        from .report_generator import ReportGenerator
        return ReportGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def create_audit_pipeline(audit_type: str, config: dict = None):
    """
    创建完整的审计流程
    
    Args:
        audit_type: 审计类型 (公共机构、公共建筑、工业企业)
        config: 配置字典
        
    Returns:
        审计流程实例
    """
    pipeline = EnergyAuditPipeline(audit_type, config)
    return pipeline


class EnergyAuditPipeline:
    """能源审计流程"""
    
    def __init__(self, audit_type: str, config: dict = None):
        """
        初始化审计流程
        
        Args:
            audit_type: 审计类型
            config: 配置字典
        """
        self.audit_type = audit_type
        self.config = config or {}
        
        # 初始化各个组件（方法内导入，避免顶层无条件加载重依赖）
        self.excel_processor = None
        self.pg_query = None
        self.rag_retrieval = None
        from tools.energy_audit import ReportGenerator
        self.report_generator = ReportGenerator(audit_type)
        
        # 数据存储
        self.raw_data = {}
        self.processed_data = {}
        self.analysis_results = {}
        self.report_data = {}
    
    def load_excel_data(self, file_path: str, sheet_name: str = None):
        """
        加载Excel数据
        
        Args:
            file_path: Excel文件路径
            sheet_name: 工作表名称
        """
        from tools.energy_audit import ExcelDataProcessor
        self.excel_processor = ExcelDataProcessor(file_path)
        data = self.excel_processor.read_excel(sheet_name)
        self.raw_data['excel'] = data
        return data
    
    def connect_database(self, db_config: dict = None):
        """
        连接数据库

        Args:
            db_config: 数据库配置（缺省/缺项时走 db_config 解析链）
        """
        config = db_config or self.config.get('database') or None
        from tools.energy_audit import PgDataQuery
        self.pg_query = PgDataQuery(config)
        self.pg_query.connect()
    
    def query_energy_data(self, start_date: str = None, end_date: str = None):
        """
        查询能耗数据
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
        """
        if not self.pg_query:
            raise Exception("请先连接数据库")
        
        data = self.pg_query.get_energy_consumption(start_date, end_date)
        self.raw_data['energy'] = data
        return data
    
    def initialize_rag(self, collection_name: str = None):
        """
        初始化RAG系统
        
        Args:
            collection_name: 集合名称
        """
        from tools.energy_audit import RAGKnowledgeRetrieval
        self.rag_retrieval = RAGKnowledgeRetrieval(collection_name)
        self.rag_retrieval.initialize()
    
    def search_knowledge(self, query: str):
        """
        搜索知识库
        
        Args:
            query: 查询内容
            
        Returns:
            检索结果
        """
        if not self.rag_retrieval:
            raise Exception("请先初始化RAG系统")
        
        return self.rag_retrieval.search(query)
    
    def process_data(self):
        """处理数据"""
        if self.excel_processor and 'excel' in self.raw_data:
            self.processed_data['excel'] = self.excel_processor.clean_data()
        
        # 可以添加更多数据处理逻辑
    
    def analyze_energy_consumption(self):
        """分析能耗数据"""
        if 'energy' in self.raw_data:
            energy_data = self.raw_data['energy']
            
            # 计算能耗指标
            analysis = {
                'total_consumption': energy_data['consumption'].sum() if 'consumption' in energy_data.columns else 0,
                'average_consumption': energy_data['consumption'].mean() if 'consumption' in energy_data.columns else 0,
                'data_count': len(energy_data)
            }
            
            self.analysis_results['consumption'] = analysis
            return analysis
        
        return {}
    
    def generate_report(self, output_path: str = None):
        """
        生成报告
        
        Args:
            output_path: 输出路径
        """
        # 设置报告数据
        self.report_generator.set_report_data(self.report_data)
        
        # 生成报告
        report_content = self.report_generator.generate_full_report()
        
        # 保存报告
        if output_path:
            self.report_generator.save_report(output_path)
        
        return report_content
    
    def run_full_pipeline(self, 
                         excel_path: str = None,
                         db_config: dict = None,
                         start_date: str = None,
                         end_date: str = None,
                         output_path: str = None):
        """
        运行完整审计流程
        
        Args:
            excel_path: Excel文件路径
            db_config: 数据库配置
            start_date: 开始日期
            end_date: 结束日期
            output_path: 输出路径
        """
        print(f"开始{self.audit_type}能源审计流程...")
        
        # 1. 加载数据
        if excel_path:
            print("加载Excel数据...")
            self.load_excel_data(excel_path)
        
        if db_config:
            print("连接数据库...")
            self.connect_database(db_config)
            print("查询能耗数据...")
            self.query_energy_data(start_date, end_date)
        
        # 2. 处理数据
        print("处理数据...")
        self.process_data()
        
        # 3. 分析数据
        print("分析能耗数据...")
        self.analyze_energy_consumption()
        
        # 4. 生成报告
        print("生成审计报告...")
        report = self.generate_report(output_path)
        
        print("审计流程完成！")
        return report


# 配置示例（凭据从环境变量读取，切勿在此写入）
# RAG 连接信息走 rag.config → config.yaml knowledge_base:（与 Desktop 知识库同一套）
DEFAULT_CONFIG = {
    'database': {
        'host': os.environ.get('DB_HOST', '10.10.1.165'),
        'port': os.environ.get('DB_PORT', '5432'),
        'database': os.environ.get('DB_NAME', 'dc_energy_audit2'),
        'user': os.environ.get('DB_USER', 'postgres'),
        'password': os.environ.get('DB_PASSWORD', ''),
        'sslmode': os.environ.get('DB_SSLMODE', 'prefer'),
    },
    'output': {
        'format': 'markdown',
        'directory': './reports',
    },
}
