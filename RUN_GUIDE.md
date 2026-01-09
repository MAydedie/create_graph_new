# 🚀 代码分析工具 - 运行和调试指南

## 📋 修复内容总结

已解决**卡顿在进度0%**的问题，修改内容包括：

### 1. ✅ app.py 修改
- **禁用debug模式** - `debug=False` 防止进程中断
- **启用线程支持** - `threaded=True` 支持并发请求
- **添加进度初始化** - 分析开始时立即设置进度为10%
- **完善日志缓冲** - 添加 `sys.stdout.flush()` 强制刷新日志到终端
- **错误追踪** - 使用 `traceback.print_exc(file=sys.stdout)` 输出完整错误栈

### 2. ✅ templates/index.html 修改
- **增加前端日志** - 浏览器控制台显示详细的状态检查日志
- **调整检查间隔** - 从500ms改为1000ms，减少频繁请求
- **改进状态监控** - 添加检查计数器，便于追踪进度

## 🎯 使用方法

### 第一步：运行应用
```bash
python app.py
```

### 第二步：查看终端日志
运行后，终端会显示详细的分析进度：

```
============================================================
[app.py] 🚀 开始分析项目: d:/代码仓库生图/create_graph
============================================================
[app.py] 初始化分析器...
[app.py] ✅ 分析器初始化完成
[app.py] 进度: 20% - 扫描项目文件...
[app.py] 开始分析代码...
[CodeAnalyzer.analyze] 正在扫描Python文件...
[CodeAnalyzer.analyze] ✓ 找到 22 个Python文件
[CodeAnalyzer.analyze] 开始解析文件...
[CodeAnalyzer.analyze]   [1/22] 解析: app.py
[CodeAnalyzer.analyze]   [2/22] 解析: analyzer.py
...
```

### 第三步：访问浏览器
```
http://localhost:5000
```

### 第四步：打开浏览器控制台查看前端日志
1. 按 `F12` 打开开发者工具
2. 点击 `Console` 选项卡
3. 查看实时的分析进度：

```
[状态检查 #1] 进度: 10% | 状态: 初始化分析器... | 分析中: true
[状态检查 #2] 进度: 20% | 状态: 正在扫描项目... | 分析中: true
[状态检查 #3] 进度: 20% | 状态: 开始分析代码... | 分析中: true
...
✅ 分析完成，加载结果数据...
```

## 🔍 调试技巧

### 如果进度还是停留在0%

**检查1：确认线程创建成功**
- 终端会显示 `[app.py] 🚀 开始分析项目: xxx`
- 如果没有这条消息，说明后台线程没有启动

**检查2：查看API响应状态**
- 打开浏览器控制台的 `Network` 标签
- 监看 `/api/status` 请求的响应数据
- 应该看到 `progress` 从0逐渐增加到100

**检查3：检查是否有异常错误**
- 查看终端是否有红色的错误信息
- 查看浏览器控制台是否有JavaScript错误

### 如果分析过程中出现错误

**查看完整错误信息**：
```bash
# 错误会打印到终端，格式为：
[app.py] ❌ 分析出错
[app.py] 错误类型: TypeError
[app.py] 错误信息: ...
```

**浏览器界面**会显示：
```
❌ 分析出错: [具体错误信息]
```

### 监视文件解析进度

查看终端的解析日志：
```
[CodeAnalyzer.analyze]   [1/22] 解析: app.py
[CodeAnalyzer.analyze]   [2/22] 解析: analyzer.py
[CodeAnalyzer.analyze]   [3/22] 解析: call_graph_analyzer.py
...
```

## 📊 完整的分析流程展示

### 终端输出示例：
```
============================================================
[app.py] 🚀 开始分析项目: d:/代码仓库生图/create_graph
============================================================
[app.py] 初始化分析器...
[CodeAnalyzer] 初始化分析器，项目路径: d:/代码仓库生图/create_graph
[CodeAnalyzer] PythonParser 初始化成功
[CodeAnalyzer] SymbolTable 绑定成功
[app.py] ✅ 分析器初始化完成
[app.py] 进度: 20% - 扫描项目文件...
[app.py] 开始分析代码...
[CodeAnalyzer.analyze] 正在扫描Python文件...
[CodeAnalyzer.analyze] ✓ 找到 22 个Python文件
[CodeAnalyzer.analyze] 开始解析文件...
[CodeAnalyzer.analyze]   [1/22] 解析: app.py
[CodeAnalyzer.analyze]   [2/22] 解析: analyzer.py
...
[CodeAnalyzer.analyze] ✓ 所有文件解析完成
[CodeAnalyzer.analyze] ========== Phase 2: 高级分析 ==========
[CodeAnalyzer.analyze] 1/4 运行调用图分析器...
[CallGraphAnalyzer] 开始构建调用图...
[CallGraphAnalyzer] ✓ 调用图构建完成
[CallGraphAnalyzer]   - 方法数: 24
[CallGraphAnalyzer]   - 调用关系数: 1171
[CodeAnalyzer.analyze] 2/4 运行继承关系分析器...
[InheritanceAnalyzer] 开始构建继承关系图...
[InheritanceAnalyzer] ✓ 继承关系图构建完成
[InheritanceAnalyzer]   - 继承关系数: 8
[CodeAnalyzer.analyze] 3/4 运行跨文件依赖分析器...
[CrossFileAnalyzer] 分析跨文件调用...
[CrossFileAnalyzer] ✓ 跨文件调用分析完成
[CrossFileAnalyzer]   - 跨文件调用数: 58
[CodeAnalyzer.analyze] 4/4 运行数据流分析器...
[DataFlowAnalyzer] 分析字段访问...
[DataFlowAnalyzer] ✓ 字段访问分析完成
[DataFlowAnalyzer]   - 字段访问关系数: 0
[app.py] ✅ 代码分析完成
[app.py]   - 节点数: 178
[app.py]   - 边数: 1405
[app.py] 进度: 90% - 生成可视化数据...
[app.py] 进度: 100% - 分析完成！
============================================================
[app.py] ✅✅✅ 分析成功完成！
============================================================
```

### 浏览器控制台输出示例：
```javascript
[状态检查 #1] 进度: 10% | 状态: 初始化分析器... | 分析中: true
[状态检查 #2] 进度: 20% | 状态: 正在扫描项目... | 分析中: true
[状态检查 #3] 进度: 20% | 状态: 开始分析代码... | 分析中: true
[状态检查 #4] 进度: 20% | 状态: 开始分析代码... | 分析中: true
...
✅ 分析完成，加载结果数据...
```

## ⚙️ 常见问题

### Q: 为什么改了debug=False？
A: debug=True会导致Flask的reloader每次检测到文件变化都会重启进程，中断后台分析线程，导致进度卡顿。

### Q: 为什么改了检查间隔从500ms到1000ms？
A: 减少前端对/api/status的请求频率，避免过多的HTTP请求影响分析性能。

### Q: 为什么要添加sys.stdout.flush()？
A: Python的print在管道缓冲时不会立即显示，flush强制将日志实时输出到终端。

### Q: 进度应该需要多长时间？
A: 取决于项目大小：
- 小项目（<10文件）：几秒钟
- 中等项目（10-50文件）：10-30秒
- 大型项目（>50文件）：1-5分钟

## 🎨 四种视图说明

分析完成后，可切换四种视图：

1. **综合视图** - 显示所有节点和关系
2. **方法调用图** - 只显示方法间的调用（橙色箭头）
3. **字段访问图** - 只显示方法对字段的访问（红色箭头）
4. **跨文件依赖** - 只显示不同文件间的依赖（绿色粗线）

## 📈 性能优化建议

如果分析速度太慢：

1. **跳过大文件** - 编辑 `_find_python_files()` 添加文件大小限制
2. **并行解析** - 使用多进程加速文件解析
3. **缓存结果** - 添加缓存避免重复分析
4. **增量分析** - 只分析修改过的文件

---

**已确认修复✅** - 现在应该能看到进度实时更新！
