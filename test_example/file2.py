"""
测试文件2 - 包含ClassB，调用ClassA的方法
"""

from file1 import ClassA


class ClassB:
    """测试类B"""
    
    def __init__(self):
        """初始化"""
        self.a = ClassA()
    
    def methodC(self):
        """方法C - 调用ClassA的methodA"""
        print("方法C执行")
        self.a.methodA()
    
    def methodD(self):
        """方法D - 调用methodC"""
        print("方法D执行")
        self.methodC()
