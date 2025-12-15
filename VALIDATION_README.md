# Lean 4 训练数据验证系统

## 概述

这个验证系统用于确保训练数据中的 Lean 4 代码能够通过编译。只有通过 Lean 4 编译器验证的数据才会被保留用于模型训练。

## 先决条件

1. **Lean 4 环境**: 确保已安装 Lean 4 和 Lake
2. **Lean 项目**: `lean_gym/` 目录下有有效的 Lean 项目配置
3. **⚠️ Mathlib 已构建**: **必须先构建 Mathlib（只需一次）**:
   ```powershell
   cd lean_gym
   lake build Mathlib
   ```
   **注意**: 首次构建 Mathlib 需要数小时，但只需执行一次。后续验证会复用已编译的库。
4. **Python 环境**: Python 3.8+

## 功能特性

- ✅ 自动提取训练数据中的 Lean 代码
- ✅ 使用 Lean 4 编译器进行真实编译验证
- ✅ 并行验证提高效率
- ✅ 详细的错误日志记录
- ✅ 进度条显示验证进度
- ✅ 自动过滤无效数据

## 文件结构

```
src/data_gen/validate_lean_code.py  # 核心验证模块
test_validation.py                   # 快速测试脚本
validate_training_data.ps1           # Windows 验证脚本
```

## 使用方法

### 1. 快速测试(验证前5个样本)

```bash
python test_validation.py
```

### 2. 验证所有数据

#### Windows PowerShell:

```powershell
# 默认配置
.\validate_training_data.ps1

# 自定义配置
.\validate_training_data.ps1 `
    -InputFile "data/step3_consensus_v2/enhanced_consensus.jsonl" `
    -OutputFile "data/validated/consensus_valid.jsonl" `
    -MaxWorkers 4 `
    -Timeout 60
```

#### Linux/Mac:

```bash
python src/data_gen/validate_lean_code.py \
    --input data/step3_consensus_v2/enhanced_consensus.jsonl \
    --output data/validated/consensus_valid.jsonl \
    --max-workers 4 \
    --timeout 60
```

### 3. 验证部分数据(用于测试)

```bash
python src/data_gen/validate_lean_code.py \
    --input data/step3_consensus_v2/enhanced_consensus.jsonl \
    --output data/validated/test_valid.jsonl \
    --max-samples 100 \
    --max-workers 2
```

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--input` | 输入 JSONL 文件路径 | 必需 |
| `--output` | 输出 JSONL 文件路径 | 必需 |
| `--lean-project` | Lean 项目路径 | `lean_gym` |
| `--max-workers` | 并行验证线程数 | 4 |
| `--max-samples` | 最大验证样本数(0=全部) | None |
| `--timeout` | 单个样本编译超时(秒) | 30 |

## 工作原理

### 验证流程

```
输入数据 → 提取 Lean 代码 → 创建临时文件 → Lean 编译 → 判断结果
   ↓                                                      ↓
跳过无代码                                         通过 → 保存
                                                   失败 → 记录错误
```

### 代码提取策略

验证器会尝试从以下字段提取 Lean 代码:
- `final_skeleton`
- `skeleton`
- `lean_code`
- `code`
- `proof`
- `theorem`

如果同时存在 `theorem` 和 `proof` 字段,会自动组合成完整定理。

### 验证机制

1. **临时文件创建**: 在 `lean_gym/LeanGym/TempValidation.lean` 创建临时文件
2. **导入必要库**: 自动添加 `import Mathlib`
3. **编译验证**: 执行 `lake build LeanGym.TempValidation`
4. **结果判定**: 
   - 返回码 = 0 → 通过
   - 返回码 ≠ 0 → 失败
   - 超时 → 失败
5. **清理**: 删除临时文件

## 输出说明

### 有效数据文件

保存所有通过验证的数据,格式与输入相同(JSONL)。

### 错误日志文件

文件名: `{output_stem}_errors.jsonl`

每行记录一个错误:
```json
{
  "theorem": "theorem_name",
  "error": "编译错误信息或异常信息"
}
```

### 验证统计

```
总样本数: 1000
有效样本: 850 (85.00%)
无效样本: 120 (12.00%)
无代码样本: 30
```

## 常见问题

### 1. 编译超时

**问题**: 某些复杂证明编译时间过长

**解决**: 增加 `--timeout` 参数值,例如:
```bash
--timeout 120  # 增加到120秒
```

### 2. 内存不足

**问题**: 并行验证导致内存不足

**解决**: 减少 `--max-workers` 参数值:
```bash
--max-workers 2  # 减少到2个线程
```

### 3. Lean 项目配置错误

**问题**: 找不到 `lakefile.lean`

**解决**: 确保 `lean_gym` 目录存在且配置正确:
```bash
cd lean_gym
lake build  # 先构建一次项目
```

### 4. 导入错误

**问题**: 缺少 Mathlib 或其他依赖

**解决**: 更新 Lean 项目依赖:
```bash
cd lean_gym
lake update
lake build
```

## 性能优化建议

### 并行配置

- **CPU 核心数少(≤4)**: `--max-workers 2`
- **CPU 核心数中等(4-8)**: `--max-workers 4`
- **CPU 核心数多(≥8)**: `--max-workers 6-8`

### 超时设置

- **简单定理**: `--timeout 30`
- **中等复杂度**: `--timeout 60`
- **复杂证明**: `--timeout 120`

## 开发说明

### 添加新的代码提取字段

在 `LeanCodeValidator.extract_lean_code()` 方法中添加:

```python
possible_fields = [
    'final_skeleton',
    'your_new_field',  # 添加新字段
    # ...
]
```

### 自定义验证逻辑

修改 `LeanCodeValidator.validate_code()` 方法。

### 扩展错误处理

在 `validate_dataset()` 方法中添加异常处理逻辑。

## 许可证

与主项目相同

## 联系方式

如有问题,请提交 Issue 或 PR。
