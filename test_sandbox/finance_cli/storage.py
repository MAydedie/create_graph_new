import json
import os
import tempfile
from typing import Optional
from pathlib import Path


class Storage:
    """
    存储层类，负责所有与ledger.json文件的交互
    实现原子性读写操作和错误处理
    """
    
    def __init__(self, file_path: str = "ledger.json"):
        """
        初始化Storage实例
        
        Args:
            file_path: ledger.json文件路径，默认为当前目录下的ledger.json
        """
        self.file_path = Path(file_path)
        
    def load(self) -> dict:
        """
        从文件加载数据到字典对象
        
        Returns:
            dict: 加载的数据字典，如果文件不存在或为空则返回空字典
            
        Raises:
            json.JSONDecodeError: 当JSON格式错误时抛出
            IOError: 当文件读取失败时抛出
        """
        try:
            # 检查文件是否存在
            if not self.file_path.exists():
                print(f"文件 {self.file_path} 不存在，返回空数据")
                return {}
            
            # 检查文件是否为空
            if self.file_path.stat().st_size == 0:
                print(f"文件 {self.file_path} 为空，返回空数据")
                return {}
            
            # 读取文件内容
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            print(f"成功从 {self.file_path} 加载数据")
            return data
            
        except json.JSONDecodeError as e:
            print(f"JSON解析错误: {e}，文件 {self.file_path} 可能已损坏")
            raise
        except IOError as e:
            print(f"文件读取错误: {e}")
            raise
        
    def save(self, data: dict) -> bool:
        """
        将数据字典保存到文件，使用原子写入确保数据一致性
        
        Args:
            data: 要保存的数据字典
            
        Returns:
            bool: 保存是否成功
            
        Raises:
            IOError: 当文件写入失败时抛出
        """
        try:
            # 创建临时文件进行原子写入
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding='utf-8',
                delete=False,
                suffix='.json',
                dir=self.file_path.parent
            ) as temp_file:
                # 将数据写入临时文件
                json.dump(data, temp_file, ensure_ascii=False, indent=2)
                temp_path = temp_file.name
            
            # 确保目标目录存在
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 原子性替换：将临时文件重命名为目标文件
            # 在Windows上可能需要先删除目标文件
            if os.name == 'nt' and self.file_path.exists():
                os.remove(self.file_path)
            
            os.replace(temp_path, self.file_path)
            
            print(f"成功保存数据到 {self.file_path}")
            return True
            
        except (IOError, OSError) as e:
            print(f"文件保存错误: {e}")
            # 清理临时文件
            if 'temp_path' in locals() and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            raise
        
    def backup(self, backup_suffix: str = ".backup") -> bool:
        """
        创建当前文件的备份
        
        Args:
            backup_suffix: 备份文件后缀，默认为".backup"
            
        Returns:
            bool: 备份是否成功
        """
        try:
            if not self.file_path.exists():
                print(f"源文件 {self.file_path} 不存在，无需备份")
                return False
                
            backup_path = self.file_path.with_suffix(backup_suffix)
            
            # 复制文件内容
            with open(self.file_path, 'r', encoding='utf-8') as src, \
                 open(backup_path, 'w', encoding='utf-8') as dst:
                dst.write(src.read())
                
            print(f"成功创建备份文件: {backup_path}")
            return True
            
        except IOError as e:
            print(f"备份失败: {e}")
            return False
    
    def exists(self) -> bool:
        """
        检查文件是否存在
        
        Returns:
            bool: 文件是否存在
        """
        return self.file_path.exists()
    
    def get_file_info(self) -> dict:
        """
        获取文件信息
        
        Returns:
            dict: 包含文件大小、修改时间等信息的字典
        """
        if not self.exists():
            return {"exists": False}
            
        stat = self.file_path.stat()
        return {
            "exists": True,
            "size": stat.st_size,
            "modified_time": stat.st_mtime,
            "path": str(self.file_path.absolute())
        }


# 使用示例
if __name__ == "__main__":
    # 创建Storage实例
    storage = Storage("ledger.json")
    
    # 检查文件是否存在
    print(f"文件存在: {storage.exists()}")
    
    # 获取文件信息
    info = storage.get_file_info()
    print(f"文件信息: {info}")
    
    # 加载数据
    try:
        data = storage.load()
        print(f"加载的数据: {data}")
    except Exception as e:
        print(f"加载失败: {e}")
        data = {"transactions": [], "metadata": {"version": "1.0"}}
    
    # 修改数据
    if "transactions" not in data:
        data["transactions"] = []
    data["transactions"].append({
        "id": 1,
        "amount": 100.0,
        "description": "测试交易"
    })
    
    # 保存数据
    try:
        success = storage.save(data)
        print(f"保存成功: {success}")
    except Exception as e:
        print(f"保存失败: {e}")
    
    # 创建备份
    storage.backup()