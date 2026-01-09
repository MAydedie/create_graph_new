"""
测试文件1 - 包含ClassA，有methodA和methodB
"""


class ClassA:
    """测试类A"""
    
    def methodA(self):
        """方法A - 调用methodB"""
        print("方法A执行")
        self.methodB()
    
    def methodB(self):
        """方法B - 调用其他方法"""
        print("方法B执行")
