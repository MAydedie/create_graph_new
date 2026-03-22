"""
数据加载模块
功能：从Excel文件读取Q&A数据，进行清洗和预处理
"""
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
from typing import List, Dict, Optional
import os


class DataLoader:
    """数据加载器类"""
    
    def __init__(self, file_path: str):
        """
        初始化数据加载器
        
        Args:
            file_path: Excel文件路径
        """
        self.file_path = file_path
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
    
    def read_excel_xml(self) -> List[List[str]]:
        """
        使用XML方式读取Excel文件（兼容性更好）
        
        Returns:
            二维列表，每行是一个列表，包含各列的值
        """
        rows = []
        
        with zipfile.ZipFile(self.file_path, 'r') as z:
            # 读取共享字符串
            shared_strings = []
            if 'xl/sharedStrings.xml' in z.namelist():
                with z.open('xl/sharedStrings.xml') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                    for si in root.findall('.//main:si', ns):
                        text_parts = []
                        for t in si.findall('.//main:t', ns):
                            if t.text:
                                text_parts.append(t.text)
                        shared_strings.append(''.join(text_parts))
            
            # 读取第一个工作表
            sheet_files = [f for f in z.namelist() if f.startswith('xl/worksheets/sheet')]
            if not sheet_files:
                raise ValueError("Excel文件中没有找到工作表")
            
            with z.open(sheet_files[0]) as f:
                tree = ET.parse(f)
                root = tree.getroot()
                ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                
                for row in root.findall('.//main:row', ns):
                    row_data = []
                    for cell in row.findall('.//main:c', ns):
                        cell_type = cell.get('t')
                        value_elem = cell.find('main:v', ns)
                        
                        if value_elem is not None and value_elem.text:
                            if cell_type == 's':  # 共享字符串
                                try:
                                    idx = int(value_elem.text)
                                    row_data.append(shared_strings[idx] if idx < len(shared_strings) else '')
                                except ValueError:
                                    row_data.append('')
                            else:
                                row_data.append(value_elem.text)
                        else:
                            row_data.append('')
                    
                    if any(row_data):  # 只保留非空行
                        rows.append(row_data)
        
        return rows
    
    def clean_text(self, text: str) -> str:
        """
        清洗文本数据
        
        Args:
            text: 原始文本
            
        Returns:
            清洗后的文本
        """
        if not text or pd.isna(text):
            return ''
        
        # 转换为字符串
        text = str(text).strip()
        
        # 移除多余的空白字符
        text = ' '.join(text.split())
        
        return text
    
    def load_data(self) -> List[Dict[str, str]]:
        """
        加载并清洗数据
        
        Returns:
            包含问题和答案对的字典列表
            格式: [{"question": "问题", "answer": "答案", "row_id": 行号}, ...]
        """
        print(f"正在读取Excel文件: {self.file_path}")
        
        # 读取原始数据
        rows = self.read_excel_xml()
        
        if len(rows) < 2:
            raise ValueError("Excel文件数据不足，至少需要表头和数据行")
        
        # 第一行是表头
        headers = rows[0]
        data_rows = rows[1:]
        
        print(f"读取到 {len(data_rows)} 行数据")
        
        # 确定问题列和答案列的索引
        question_col_idx = 0  # A列（索引0）
        answer_col_idx = 1   # B列（索引1）
        
        # 如果表头有名称，尝试根据表头确定列
        if len(headers) > 0:
            for idx, header in enumerate(headers):
                header_str = str(header).strip().lower()
                if '问题' in header_str or 'question' in header_str:
                    question_col_idx = idx
                elif '答案' in header_str or 'answer' in header_str:
                    answer_col_idx = idx
        
        # 处理数据
        qa_pairs = []
        skipped_count = 0
        
        for row_idx, row in enumerate(data_rows, start=2):  # 从第2行开始（Excel行号）
            # 确保行有足够的列
            while len(row) <= max(question_col_idx, answer_col_idx):
                row.append('')
            
            question = self.clean_text(row[question_col_idx] if question_col_idx < len(row) else '')
            answer = self.clean_text(row[answer_col_idx] if answer_col_idx < len(row) else '')
            
            # 跳过问题和答案都为空的行
            if not question and not answer:
                skipped_count += 1
                continue
            
            # 如果只有问题没有答案，或者只有答案没有问题，仍然保留（可能有用）
            qa_pairs.append({
                "question": question,
                "answer": answer,
                "row_id": row_idx,  # Excel中的实际行号
                "source": os.path.basename(self.file_path)
            })
        
        print(f"成功加载 {len(qa_pairs)} 条Q&A对")
        if skipped_count > 0:
            print(f"跳过 {skipped_count} 条空数据")
        
        return qa_pairs
    
    def get_statistics(self, qa_pairs: List[Dict[str, str]]) -> Dict:
        """
        获取数据统计信息
        
        Args:
            qa_pairs: Q&A对列表
            
        Returns:
            统计信息字典
        """
        if not qa_pairs:
            return {}
        
        question_lengths = [len(item['question']) for item in qa_pairs if item['question']]
        answer_lengths = [len(item['answer']) for item in qa_pairs if item['answer']]
        
        stats = {
            "total_pairs": len(qa_pairs),
            "with_question": sum(1 for item in qa_pairs if item['question']),
            "with_answer": sum(1 for item in qa_pairs if item['answer']),
            "question_avg_length": sum(question_lengths) / len(question_lengths) if question_lengths else 0,
            "answer_avg_length": sum(answer_lengths) / len(answer_lengths) if answer_lengths else 0,
            "question_max_length": max(question_lengths) if question_lengths else 0,
            "answer_max_length": max(answer_lengths) if answer_lengths else 0,
        }
        
        return stats


def load_qa_data(file_path: str) -> List[Dict[str, str]]:
    """
    便捷函数：加载Q&A数据
    
    Args:
        file_path: Excel文件路径
        
    Returns:
        Q&A对列表
    """
    loader = DataLoader(file_path)
    return loader.load_data()


if __name__ == "__main__":
    # 测试代码
    file_path = r"资料\喜哥帮AI客服Q&A【知识库】20260119.xlsx"
    
    try:
        loader = DataLoader(file_path)
        qa_pairs = loader.load_data()
        
        # 显示统计信息
        stats = loader.get_statistics(qa_pairs)
        print("\n" + "=" * 60)
        print("数据统计信息")
        print("=" * 60)
        for key, value in stats.items():
            if isinstance(value, float):
                print(f"{key}: {value:.2f}")
            else:
                print(f"{key}: {value}")
        
        # 显示前3条数据示例
        print("\n" + "=" * 60)
        print("前3条数据示例")
        print("=" * 60)
        for i, item in enumerate(qa_pairs[:3], 1):
            print(f"\n【示例 {i}】")
            print(f"行号: {item['row_id']}")
            print(f"问题: {item['question']}")
            print(f"答案: {item['answer'][:100]}..." if len(item['answer']) > 100 else f"答案: {item['answer']}")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()



