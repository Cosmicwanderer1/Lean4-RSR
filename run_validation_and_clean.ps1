# 训练数据验证和清理脚本
# 自动验证训练数据并删除不正确的样本

param(
    [string]$InputFile = "data/step3_consensus_v2/enhanced_consensus.jsonl",
    [string]$OutputFile = "data/validated/consensus_valid.jsonl",
    [int]$MaxSamples = 0,  # 0 = 全部
    [int]$MaxWorkers = 1,   # 建议使用1以获得更稳定的输出
    [int]$Timeout = 60,
    [switch]$NoSaveInvalid,
    [switch]$Debug
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "训练数据验证和清理工具" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查输入文件
if (-not (Test-Path $InputFile)) {
    Write-Host "错误: 输入文件不存在: $InputFile" -ForegroundColor Red
    exit 1
}

# 检查 Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "错误: 未找到 Python" -ForegroundColor Red
    exit 1
}

# 构建命令参数
$args = @(
    "validate_and_clean_training_data.py",
    "--input", $InputFile,
    "--output", $OutputFile,
    "--max-workers", $MaxWorkers,
    "--timeout", $Timeout
)

if ($MaxSamples -gt 0) {
    $args += "--max-samples", $MaxSamples
}

if ($NoSaveInvalid) {
    $args += "--no-save-invalid"
}

if ($Debug) {
    $args += "--debug"
}

# 显示配置
Write-Host "配置信息:" -ForegroundColor Green
Write-Host "  输入文件: $InputFile"
Write-Host "  输出文件: $OutputFile"
Write-Host "  验证样本: $(if ($MaxSamples -gt 0) { "$MaxSamples 个" } else { "全部" })"
Write-Host "  并行数量: $MaxWorkers"
Write-Host "  超时时间: $Timeout 秒"
Write-Host "  保存错误: $(if ($NoSaveInvalid) { '否' } else { '是' })"
Write-Host ""

# 运行验证
Write-Host "开始验证..." -ForegroundColor Yellow
python @args

$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host ""
    Write-Host "验证成功完成!" -ForegroundColor Green
    Write-Host ""
    Write-Host "生成的文件:" -ForegroundColor Cyan
    Write-Host "  - 有效数据: $OutputFile" -ForegroundColor Green
    
    $errorFile = Join-Path (Split-Path $OutputFile) "$((Get-Item $OutputFile).BaseName)_errors.jsonl"
    if (Test-Path $errorFile) {
        Write-Host "  - 错误详情: $errorFile" -ForegroundColor Yellow
    }
    
    $reportFile = Join-Path (Split-Path $OutputFile) "$((Get-Item $OutputFile).BaseName)_report.txt"
    if (Test-Path $reportFile) {
        Write-Host "  - 验证报告: $reportFile" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "报告摘要:" -ForegroundColor Cyan
        Get-Content $reportFile | Select-Object -First 15
    }
} else {
    Write-Host ""
    Write-Host "验证过程出现错误" -ForegroundColor Red
}

exit $exitCode
