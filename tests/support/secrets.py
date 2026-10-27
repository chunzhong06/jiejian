# 集成测试使用进程内秘密引用，禁止访问用户的系统凭据管理器。
class MemorySecrets:
    def __init__(self):self.values={}
    def write(self,reference,value):self.values[reference]=value
    def read(self,reference):return self.values.get(reference)
    def delete(self,reference):self.values.pop(reference,None)
    def configured(self,reference):return bool(reference and reference in self.values)
