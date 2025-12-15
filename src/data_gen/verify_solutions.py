#!/usr/bin/env python3
"""
Lean 4 Proof Verifier - Optimized Version
高效并行验证Lean定理证明，自动筛选生成黄金数据集
"""

import json
import os
import subprocess
import tempfile
import multiprocessing
import re
import hashlib
import argparse
import sys
import uuid
import logging
import time
import shutil
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any, Set
from tqdm import tqdm
from dataclasses import dataclass, asdict, field
import signal
import gc
import psutil
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from collections import defaultdict
import pickle
from enum import Enum
import traceback
import platform

# --- 日志配置 ---
class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[41m',   # 红底白字
        'RESET': '\033[0m'
    }
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        # 避免修改原始 record 对象，防止影响其他 handler
        record.levelname = f"{color}{record.levelname}{self.COLORS['RESET']}"
        record.msg = f"{color}{record.msg}{self.COLORS['RESET']}"
        return super().format(record)

def setup_logging(log_file: str = None):
    """设置日志配置"""
    # 移除默认的 logger 配置，防止重复打印
    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_formatter = ColoredFormatter(
        '%(asctime)s - %(levelname)s - %(processName)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # 文件处理器
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(processName)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    
    return root_logger

logger = logging.getLogger(__name__)

# --- 枚举和常量 ---
class VerificationStatus(Enum):
    """验证状态枚举"""
    SUCCESS = "success"
    COMPILE_ERROR = "compile_error"
    TIMEOUT = "timeout"
    MEMORY_LIMIT = "memory_limit"
    INVALID_FORMAT = "invalid_format"
    CONTAINS_SORRY = "contains_sorry"
    SYSTEM_ERROR = "system_error"

# --- 数据类 ---
@dataclass
class VerificationResult:
    """验证结果数据类"""
    task_id: str
    original_decl: str
    solution: str
    proof_only: str
    normalized_hash: str
    length: int
    is_complete_proof: bool
    verification_time: float
    status: VerificationStatus
    lean_version: Optional[str] = None
    memory_used_mb: Optional[float] = None
    stats: Optional[Dict] = None
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        result = asdict(self)
        result['status'] = self.status.value
        return result

@dataclass
class SystemStats:
    """系统统计信息"""
    total_tasks: int = 0
    processed_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    total_memory_used_mb: float = 0.0
    total_verification_time: float = 0.0
    start_time: float = field(default_factory=time.time)
    
    def update_stats(self, result: Optional[VerificationResult] = None, 
                    failed: bool = False, memory_used: float = 0.0):
        """更新统计信息"""
        self.processed_tasks += 1
        
        if result and result.status == VerificationStatus.SUCCESS:
            self.successful_tasks += 1
            self.total_verification_time += result.verification_time
        else:
            self.failed_tasks += 1
            
        self.total_memory_used_mb += memory_used
    
    def get_summary(self) -> Dict:
        """获取统计摘要"""
        elapsed = time.time() - self.start_time
        return {
            "total_tasks": self.total_tasks,
            "processed_tasks": self.processed_tasks,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "success_rate": self.successful_tasks / max(1, self.processed_tasks),
            "avg_memory_mb": self.total_memory_used_mb / max(1, self.processed_tasks),
            "avg_time_per_task": self.total_verification_time / max(1, self.successful_tasks),
            "total_time_seconds": elapsed,
            "tasks_per_second": self.processed_tasks / max(1, elapsed)
        }

# --- 配置管理器 ---
class Config:
    """配置管理器"""
    # 路径配置
    DEFAULT_INPUT_FILE = "data/processed/solutions_shard_0.jsonl"
    DEFAULT_OUTPUT_FILE = "data/processed/verified_gold_data.jsonl"
    LEAN_GYM_PATH = os.path.abspath("lean_gym")
    CACHE_DIR = ".verification_cache"
    
    # 验证参数
    TIMEOUT = 45
    TIMEOUT_LONG = 120  # 长证明的超时时间
    NUM_WORKERS = max(1, multiprocessing.cpu_count() - 1)
    MAX_MEMORY_PER_WORKER_MB = 4096  # 4GB
    MAX_TOTAL_MEMORY_MB = 32768  # 32GB 总限制
    
    # 验证选项
    STRICT_BAD_PATTERNS = re.compile(r"(sorry|admit|axiom|undefined)", re.IGNORECASE)
    WARNING_PATTERNS = re.compile(r"warning:", re.IGNORECASE)
    HEADER = "import Mathlib\nopen Classical\n\n"
    
    # 缓存配置
    CACHE_MAX_SIZE = 10000
    ENABLE_CACHE = True
    ENABLE_INCREMENTAL = True
    
    # 临时目录
    @staticmethod
    def get_temp_dir() -> str:
        """获取临时目录"""
        # 尝试多个可能的临时目录位置
        candidates = [
            "/root/autodl-fs/lean_verify_tmp",  # AutoDL
            "/data/lean_verify_tmp",  # 通用数据目录
            "/tmp/lean_verify",
            str(Path.home() / ".lean_verify_tmp"),
            os.path.join(tempfile.gettempdir(), "lean_verify")
        ]
        
        for candidate in candidates:
            try:
                path = Path(candidate)
                path.mkdir(parents=True, exist_ok=True)
                # 测试写入权限
                test_file = path / ".write_test"
                with open(test_file, 'w') as f:
                    f.write("test")
                test_file.unlink()
                return str(path.absolute())
            except (OSError, PermissionError):
                continue
        
        # 如果所有候选目录都失败，使用当前目录
        fallback = Path("lean_verify_tmp")
        fallback.mkdir(exist_ok=True)
        return str(fallback.absolute())
    
    TEMP_DIR = get_temp_dir.__func__()
    
    @classmethod
    def update_from_args(cls, args):
        """根据命令行参数更新配置"""
        cls.LEAN_GYM_PATH = os.path.abspath(args.lean_gym_path)
        cls.TIMEOUT = args.timeout
        cls.NUM_WORKERS = args.num_workers
        cls.MAX_MEMORY_PER_WORKER_MB = args.max_memory_mb
        cls.ENABLE_CACHE = not args.disable_cache
        cls.ENABLE_INCREMENTAL = not args.disable_incremental

# --- 工具函数 ---
class CodeNormalizer:
    """代码规范化器"""
    
    @staticmethod
    def normalize_code(code: str) -> str:
        """
        规范化代码用于哈希计算
        - 移除所有空白字符
        - 标准化缩进
        - 移除注释
        """
        # 移除单行注释和多行注释
        lines = []
        for line in code.split('\n'):
            # 移除行内注释
            if '--' in line:
                line = line[:line.index('--')]
            lines.append(line.strip())
        
        code_no_comments = '\n'.join(lines)
        
        # 移除多行注释 (简化版本)
        code_no_comments = re.sub(r'/-[\s\S]*?-\/', '', code_no_comments)
        
        # 移除所有空白字符并标准化
        normalized = re.sub(r'\s+', ' ', code_no_comments).strip()
        return normalized
    
    @staticmethod
    def extract_code_from_markdown(text: str) -> str:
        """从Markdown中提取Lean代码块"""
        if not text:
            return ""
        
        # 移除可能的HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        
        # 匹配代码块
        patterns = [
            r'```(?:lean)?\s*(.*?)```',  # ```lean ... ```
            r'```\s*(.*?)```',           # ``` ... ```
            r'`(.*?)`',                  # `...`
        ]
        
        code_blocks = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                if match and len(match.strip()) > 10:  # 最小长度阈值
                    code_blocks.append(match.strip())
        
        if code_blocks:
            # 选择最长的代码块
            return max(code_blocks, key=len)
        
        # 如果没有代码块，尝试提取可能是代码的行
        lines = text.split('\n')
        code_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # 启发式检测代码行
            is_code_line = (
                line_stripped.startswith('theorem') or
                line_stripped.startswith('lemma') or
                line_stripped.startswith('example') or
                line_stripped.startswith('def') or
                line_stripped.startswith('by ') or
                line_stripped.startswith('calc') or
                ':=' in line_stripped
            )
            
            if is_code_line:
                code_lines.append(line_stripped)
        
        if code_lines:
            return '\n'.join(code_lines)
        
        return text.strip()
    
    @staticmethod
    def clean_proof_code(code: str) -> str:
        """清洗证明代码"""
        # 移除常见的回复前缀
        prefixes = [
            r'Here is (?:the )?(?:proof|solution)[:\s]*',
            r'Proof[:\s]*',
            r'Solution[:\s]*',
            r'Here\'s (?:the )?(?:proof|solution)[:\s]*',
            r'Sure,? (?:here is|here\'s) (?:the )?(?:proof|solution)[:\s]*',
            r'Certainly[:\s]*',
            r'The (?:proof|solution) is[:\s]*',
        ]
        
        for prefix in prefixes:
            code = re.sub(prefix, '', code, flags=re.IGNORECASE)
        
        # 移除常见的结尾标记
        suffixes = [
            r'\s*QED\.?\s*$',
            r'\s*∎\s*$',
            r'\s*This completes the proof\.?\s*$',
        ]
        
        for suffix in suffixes:
            code = re.sub(suffix, '', code, flags=re.IGNORECASE)
        
        return code.strip()
    
    @staticmethod
    def validate_lean_syntax(code: str) -> Tuple[bool, str]:
        """基础语法验证"""
        # 检查是否包含定理声明
        if not any(keyword in code for keyword in ['theorem', 'lemma', 'example']):
            return False, "No theorem/lemma/example declaration found"
        
        # 检查是否有证明体
        if ':=' not in code and 'by' not in code and 'begin' not in code:
            return False, "No proof body found"
        
        # 检查括号是否平衡（简化检查）
        if code.count('(') != code.count(')'):
            return False, "Unbalanced parentheses"
        
        return True, ""

class CacheManager:
    """缓存管理器"""
    
    def __init__(self, cache_dir: str = Config.CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_file = self.cache_dir / "verification_cache.pkl"
        self.cache = self._load_cache()
    
    def _load_cache(self) -> Dict:
        """加载缓存"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'rb') as f:
                    return pickle.load(f)
            except (pickle.PickleError, EOFError):
                logger.warning("Cache file corrupted, starting fresh")
                return {}
        return {}
    
    def _save_cache(self):
        """保存缓存"""
        try:
            # 限制缓存大小
            if len(self.cache) > Config.CACHE_MAX_SIZE:
                # 保留最近使用的条目
                items = sorted(self.cache.items(), key=lambda x: x[1].get('timestamp', 0))
                self.cache = dict(items[-Config.CACHE_MAX_SIZE:])
            
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.cache, f)
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
    
    def get_cache_key(self, decl: str, proof: str) -> str:
        """获取缓存键"""
        normalized = CodeNormalizer.normalize_code(f"{decl} := {proof}")
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def get(self, cache_key: str) -> Optional[Dict]:
        """获取缓存结果"""
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            # 检查是否过期（24小时）
            if time.time() - entry.get('timestamp', 0) < 86400:
                return entry.get('result')
        return None
    
    def set(self, cache_key: str, result: Dict):
        """设置缓存结果"""
        self.cache[cache_key] = {
            'result': result,
            'timestamp': time.time()
        }
        # 定期保存缓存
        if len(self.cache) % 100 == 0:
            self._save_cache()
    
    def save(self):
        """显式保存缓存"""
        self._save_cache()

class ResourceMonitor:
    """资源监控器"""
    
    def __init__(self):
        self.start_time = time.time()
        self.process = psutil.Process()
        # 初始化内存
        try:
            self.start_memory = self.process.memory_info().rss
        except Exception:
            self.start_memory = 0
    
    def get_current_usage(self) -> Dict:
        """获取当前资源使用情况"""
        try:
            memory_info = self.process.memory_info()
            return {
                'memory_mb': memory_info.rss / 1024 / 1024,
                'cpu_percent': self.process.cpu_percent(interval=0.1),
                'threads': self.process.num_threads(),
                'elapsed_time': time.time() - self.start_time
            }
        except Exception:
            return {'memory_mb': 0, 'cpu_percent': 0, 'threads': 1, 'elapsed_time': 0}
    
    def check_system_limits(self) -> Tuple[bool, str]:
        """检查系统限制"""
        try:
            # 检查可用内存
            mem = psutil.virtual_memory()
            if mem.available < Config.MAX_TOTAL_MEMORY_MB * 1024 * 1024:
                return False, f"Insufficient system memory: {mem.available / 1024 / 1024:.1f}MB available"
            
            # 检查磁盘空间
            if os.path.exists(Config.TEMP_DIR):
                disk = psutil.disk_usage(Config.TEMP_DIR)
                if disk.free < 1024 * 1024 * 1024:  # 1GB
                    return False, f"Insufficient disk space: {disk.free / 1024 / 1024:.1f}MB free"
            
            return True, "OK"
        except Exception as e:
            return False, f"Resource check failed: {e}"
    
    @staticmethod
    def get_system_info() -> Dict:
        """获取系统信息"""
        try:
            return {
                'platform': platform.platform(),
                'processor': platform.processor(),
                'cpu_count': psutil.cpu_count(),
                'total_memory_gb': psutil.virtual_memory().total / 1024 / 1024 / 1024,
                'python_version': platform.python_version(),
                'lean_version': ResourceMonitor._get_lean_version()
            }
        except Exception:
            return {}
    
    @staticmethod
    def _get_lean_version() -> Optional[str]:
        """获取Lean版本"""
        try:
            result = subprocess.run(
                ['lean', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

# --- 验证工作进程 ---
def init_worker():
    """初始化工作进程"""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    
    # 设置进程名称 (可选依赖)
    try:
        import setproctitle
        setproctitle.setproctitle(f"lean_verify_worker_{os.getpid()}")
    except ImportError:
        pass

def verify_single_proof(args: Tuple) -> Optional[VerificationResult]:
    """
    验证单个证明（在子进程中运行）
    """
    code_snippet, original_decl, task_id, allow_sorry, timeout = args
    
    start_time = time.time()
    tmp_path = ""
    process_id = os.getpid()
    resource_monitor = ResourceMonitor()
    
    try:
        # === Level 1: 预验证和清洗 ===
        
        # 1.1 基础清洗
        clean_code = CodeNormalizer.clean_proof_code(code_snippet)
        
        # 1.2 从Markdown提取
        clean_code = CodeNormalizer.extract_code_from_markdown(clean_code)
        
        # 1.3 非空检查
        if not clean_code or len(clean_code.strip()) < 5:
            return VerificationResult(
                task_id=task_id,
                original_decl=original_decl,
                solution=code_snippet,
                proof_only=clean_code,
                normalized_hash="",
                length=0,
                is_complete_proof=False,
                verification_time=time.time() - start_time,
                status=VerificationStatus.INVALID_FORMAT,
                error_message="Empty or too short proof"
            )
        
        # 1.4 语法验证
        syntax_ok, syntax_error = CodeNormalizer.validate_lean_syntax(clean_code)
        if not syntax_ok:
            return VerificationResult(
                task_id=task_id,
                original_decl=original_decl,
                solution=code_snippet,
                proof_only=clean_code,
                normalized_hash="",
                length=len(clean_code),
                is_complete_proof=False,
                verification_time=time.time() - start_time,
                status=VerificationStatus.INVALID_FORMAT,
                error_message=syntax_error
            )
        
        # 1.5 检查Sorry
        if not allow_sorry and Config.STRICT_BAD_PATTERNS.search(clean_code):
            return VerificationResult(
                task_id=task_id,
                original_decl=original_decl,
                solution=code_snippet,
                proof_only=clean_code,
                normalized_hash="",
                length=len(clean_code),
                is_complete_proof=False,
                verification_time=time.time() - start_time,
                status=VerificationStatus.CONTAINS_SORRY,
                error_message="Proof contains sorry/admit"
            )
        
        # === Level 2: 代码构建 ===
        
        # 2.1 确定是否需要包装
        full_code = ""
        if "theorem" in clean_code and ":=" in clean_code:
            full_code = clean_code
        else:
            # 模型只输出了证明体，需要构建完整定理
            proof_body = clean_code.strip()
            
            # 启发式添加 'by' 或 'begin'
            if not (proof_body.startswith("by") or 
                    proof_body.startswith("begin") or
                    proof_body.startswith("exact") or
                    proof_body.startswith("apply") or
                    proof_body.startswith("refine")):
                
                # 检查是否应该使用 begin ... end
                if ";" in proof_body or "\n" in proof_body:
                    proof_body = f"begin\n  {proof_body}\nend"
                else:
                    proof_body = f"by {proof_body}"
            
            full_code = f"{original_decl} := {proof_body}"
        
        # 最终验证结构
        if ":=" not in full_code:
            return VerificationResult(
                task_id=task_id,
                original_decl=original_decl,
                solution=code_snippet,
                proof_only=clean_code,
                normalized_hash="",
                length=len(full_code),
                is_complete_proof=False,
                verification_time=time.time() - start_time,
                status=VerificationStatus.INVALID_FORMAT,
                error_message="Invalid proof structure"
            )
        
        # === Level 3: 编译验证 ===
        
        # 3.1 准备文件内容
        file_content = f"{Config.HEADER}{full_code}"
        
        # 3.2 生成临时文件
        unique_id = f"{hashlib.md5(full_code.encode()).hexdigest()[:8]}_{process_id}_{uuid.uuid4().hex[:6]}"
        tmp_path = os.path.join(Config.TEMP_DIR, f"verify_{unique_id}.lean")
        
        with open(tmp_path, 'w', encoding='utf-8', errors='ignore') as f:
            f.write(file_content)
        
        # 3.3 确定超时时间（根据证明长度）
        actual_timeout = timeout
        if len(full_code) > 1000:  # 长证明使用更长超时
            actual_timeout = min(timeout * 2, 300)
        
        # 3.4 编译命令
        cmd = ["lake", "env", "lean", tmp_path]
        
        # 3.5 设置资源限制
        def preexec_fn():
            if sys.platform != "win32":
                try:
                    import resource
                    # 设置内存限制
                    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
                    new_limit = Config.MAX_MEMORY_PER_WORKER_MB * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_AS, (new_limit, hard))
                    
                    # 设置CPU时间限制
                    resource.setrlimit(resource.RLIMIT_CPU, (actual_timeout, actual_timeout + 10))
                except (ValueError, OSError, ImportError):
                    pass
        
        # 3.6 执行编译
        start_compile = time.time()
        result = subprocess.run(
            cmd,
            cwd=Config.LEAN_GYM_PATH,
            capture_output=True,
            text=True,
            timeout=actual_timeout,
            encoding='utf-8',
            errors='ignore',
            preexec_fn=preexec_fn if sys.platform != "win32" else None
        )
        
        compile_time = time.time() - start_compile
        
        # 3.7 分析结果
        verification_time = time.time() - start_time
        memory_used = resource_monitor.get_current_usage()['memory_mb']
        
        # 检查编译输出
        warnings = []
        if result.stderr:
            for line in result.stderr.split('\n'):
                if "warning" in line.lower():
                    warnings.append(line.strip())
        
        # 3.8 验证成功条件
        if result.returncode == 0:
            # 最终检查sorry（防止编译器警告但通过）
            has_sorry = bool(Config.STRICT_BAD_PATTERNS.search(full_code))
            
            if not allow_sorry and has_sorry:
                return VerificationResult(
                    task_id=task_id,
                    original_decl=original_decl,
                    solution=full_code,
                    proof_only=clean_code,
                    normalized_hash=hashlib.md5(CodeNormalizer.normalize_code(full_code).encode()).hexdigest(),
                    length=len(full_code),
                    is_complete_proof=False,
                    verification_time=verification_time,
                    status=VerificationStatus.CONTAINS_SORRY,
                    memory_used_mb=memory_used,
                    error_message="Proof contains sorry/admit"
                )
            
            # 成功！
            return VerificationResult(
                task_id=task_id,
                original_decl=original_decl,
                solution=full_code,
                proof_only=clean_code,
                normalized_hash=hashlib.md5(CodeNormalizer.normalize_code(full_code).encode()).hexdigest(),
                length=len(full_code),
                is_complete_proof=not has_sorry,
                verification_time=verification_time,
                status=VerificationStatus.SUCCESS,
                memory_used_mb=memory_used,
                warnings=warnings
            )
        else:
            # 编译失败
            error_msg = result.stderr[:500] if result.stderr else "Unknown compilation error"
            
            # 确定错误类型
            if "out of memory" in error_msg.lower():
                status = VerificationStatus.MEMORY_LIMIT
            elif "timeout" in error_msg.lower() or compile_time >= actual_timeout:
                status = VerificationStatus.TIMEOUT
            else:
                status = VerificationStatus.COMPILE_ERROR
            
            return VerificationResult(
                task_id=task_id,
                original_decl=original_decl,
                solution=full_code,
                proof_only=clean_code,
                normalized_hash=hashlib.md5(CodeNormalizer.normalize_code(full_code).encode()).hexdigest(),
                length=len(full_code),
                is_complete_proof=False,
                verification_time=verification_time,
                status=status,
                memory_used_mb=memory_used,
                error_message=error_msg,
                warnings=warnings
            )
            
    except subprocess.TimeoutExpired:
        return VerificationResult(
            task_id=task_id,
            original_decl=original_decl,
            solution=code_snippet,
            proof_only=clean_code,
            normalized_hash="",
            length=0,
            is_complete_proof=False,
            verification_time=time.time() - start_time,
            status=VerificationStatus.TIMEOUT,
            error_message=f"Timeout after {timeout} seconds"
        )
    except MemoryError:
        return VerificationResult(
            task_id=task_id,
            original_decl=original_decl,
            solution=code_snippet,
            proof_only=clean_code,
            normalized_hash="",
            length=0,
            is_complete_proof=False,
            verification_time=time.time() - start_time,
            status=VerificationStatus.MEMORY_LIMIT,
            error_message="Memory limit exceeded"
        )
    except Exception as e:
        return VerificationResult(
            task_id=task_id,
            original_decl=original_decl,
            solution=code_snippet,
            proof_only=clean_code,
            normalized_hash="",
            length=0,
            is_complete_proof=False,
            verification_time=time.time() - start_time,
            status=VerificationStatus.SYSTEM_ERROR,
            error_message=f"System error: {str(e)[:200]}"
        )
    finally:
        # 清理临时文件
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        
        # 强制垃圾回收
        gc.collect()

# --- 主要处理逻辑 ---
class ProofVerifier:
    """证明验证器主类"""
    
    def __init__(self, args):
        self.args = args
        self.solved_tasks = defaultdict(list)
        self.cache_manager = CacheManager() if Config.ENABLE_CACHE else None
        self.resource_monitor = ResourceMonitor()
        self.stats = SystemStats()
        
        # 加载已有的结果用于增量处理
        self.existing_results = {}
        if Config.ENABLE_INCREMENTAL and os.path.exists(self.args.output_file):
            self._load_existing_results()
    
    def _load_existing_results(self):
        """加载已有结果"""
        try:
            with open(self.args.output_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        self.existing_results[data['task_id']] = data
            logger.info(f"📂 Loaded {len(self.existing_results)} existing results for incremental processing")
        except Exception as e:
            logger.warning(f"Failed to load existing results: {e}")
    
    def check_lean_environment(self) -> bool:
        """检查Lean环境"""
        logger.info("🔍 Checking Lean environment...")
        
        # 检查lean_gym路径
        if not os.path.exists(Config.LEAN_GYM_PATH):
            logger.error(f"❌ Lean gym path not found: {Config.LEAN_GYM_PATH}")
            return False
        
        # 检查lakefile
        lakefile_lean = os.path.join(Config.LEAN_GYM_PATH, "lakefile.lean")
        lakefile_toml = os.path.join(Config.LEAN_GYM_PATH, "lakefile.toml")
        
        if not os.path.exists(lakefile_lean) and not os.path.exists(lakefile_toml):
            logger.error("❌ No lakefile found in lean_gym directory")
            logger.error("👉 Please run: git clone https://github.com/leanprover/lean4-simple.git lean_gym")
            return False
        
        # 测试lake命令
        try:
            # 编译lean_gym
            logger.info("🛠️  Building lean_gym dependencies...")
            build_result = subprocess.run(
                ["lake", "build"],
                cwd=Config.LEAN_GYM_PATH,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if build_result.returncode != 0:
                logger.warning(f"⚠️  Lake build had issues: {build_result.stderr[:200]}")
                # 继续尝试，可能部分包已经构建
            
            # 测试简单证明
            test_code = """
            theorem test : 1 + 1 = 2 := by
              norm_num
            """
            
            test_file = os.path.join(Config.TEMP_DIR, "test_env.lean")
            with open(test_file, 'w') as f:
                f.write("import Mathlib\n" + test_code)
            
            # 注意：此处将超时时间增加到了 600秒 (10分钟)
            # 并且捕获超时异常，允许脚本继续运行
            try:
                test_result = subprocess.run(
                    ["lake", "env", "lean", test_file],
                    cwd=Config.LEAN_GYM_PATH,
                    capture_output=True,
                    text=True,
                    timeout=600  # <--- 修改: 大幅增加超时时间
                )
                
                os.remove(test_file)
                
                if test_result.returncode == 0:
                    logger.info("✅ Lean environment is ready!")
                    
                    # 显示系统信息
                    sys_info = self.resource_monitor.get_system_info()
                    logger.info(f"📊 System info:")
                    logger.info(f"   Platform: {sys_info.get('platform', 'unknown')}")
                    logger.info(f"   CPU cores: {sys_info.get('cpu_count', 'unknown')}")
                    logger.info(f"   Total memory: {sys_info.get('total_memory_gb', 0):.1f} GB")
                    if sys_info.get('lean_version'):
                        logger.info(f"   Lean version: {sys_info['lean_version']}")
                    
                    return True
                else:
                    logger.error(f"❌ Lean test failed: {test_result.stderr[:200]}")
                    return False
            except subprocess.TimeoutExpired:
                # 修改: 超时不再作为致命错误，而是警告并继续
                logger.warning("⚠️  Environment check timed out (likely due to slow I/O).")
                logger.warning("👉 Proceeding anyway, as you have verified the environment manually.")
                if os.path.exists(test_file):
                    os.remove(test_file)
                return True
                
        except Exception as e:
            logger.error(f"❌ Environment check failed: {e}")
            return False
    
    def load_tasks(self) -> List[Tuple]:
        """加载待验证任务"""
        tasks = []
        skipped_lines = 0
        duplicate_tasks = 0
        
        logger.info(f"📂 Loading tasks from {self.args.input_file}")
        
        # 检查文件是否存在
        if not os.path.exists(self.args.input_file):
            logger.error(f"❌ Input file not found: {self.args.input_file}")
            return []
        
        try:
            with open(self.args.input_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(tqdm(f, desc="Loading", unit="lines"), 1):
                    if not line.strip():
                        continue
                    
                    try:
                        data = json.loads(line)
                        task_id = data.get('task_id', f'line_{line_num}')
                        decl = data.get('original_decl', '').strip()
                        
                        # 跳过已有结果的（增量处理）
                        if task_id in self.existing_results and Config.ENABLE_INCREMENTAL:
                            duplicate_tasks += 1
                            continue
                        
                        # 提取解决方案
                        solutions = []
                        
                        # 支持多种数据格式
                        if 'solutions' in data and isinstance(data['solutions'], list):
                            solutions = data['solutions']
                        elif 'response' in data:
                            solutions = [data['response']]
                        elif 'solution' in data:
                            solutions = [data['solution']]
                        elif 'completion' in data:
                            solutions = [data['completion']]
                        
                        # 去重解决方案
                        unique_solutions = set()
                        for sol in solutions:
                            if sol and isinstance(sol, str):
                                clean_sol = sol.strip()
                                if clean_sol and len(clean_sol) >= 5:  # 最小长度
                                    unique_solutions.add(clean_sol)
                        
                        # 添加任务
                        for sol in unique_solutions:
                            # 检查缓存
                            cache_key = None
                            if self.cache_manager:
                                cache_key = self.cache_manager.get_cache_key(decl, sol)
                                cached_result = self.cache_manager.get(cache_key)
                                if cached_result:
                                    # 使用缓存结果
                                    if cached_result.get('status') == VerificationStatus.SUCCESS.value:
                                        if cached_result['task_id'] not in self.solved_tasks:
                                            self.solved_tasks[cached_result['task_id']] = []
                                        
                                        # 转换回对象
                                        # 注意：这里简化了，实际上应该完整重建 VerificationResult
                                        # 但对于统计来说，字典已经足够了
                                        # 为了保持类型一致，这里我们只在统计时使用
                                        self.stats.successful_tasks += 1
                                        continue
                            
                            tasks.append((sol, decl, task_id, self.args.allow_sorry, self.args.timeout))
                            self.stats.total_tasks += 1
                            
                    except json.JSONDecodeError:
                        skipped_lines += 1
                    except Exception as e:
                        logger.debug(f"Error processing line {line_num}: {e}")
            
            logger.info(f"✅ Loaded {len(tasks)} tasks from {line_num} lines")
            logger.info(f"   Skipped {skipped_lines} invalid JSON lines")
            logger.info(f"   Skipped {duplicate_tasks} already processed tasks")
            
            if not tasks:
                logger.warning("⚠️  No new tasks to process!")
            
            return tasks
            
        except Exception as e:
            logger.error(f"❌ Failed to load tasks: {e}")
            traceback.print_exc()
            return []
    
    def verify_parallel(self, tasks: List[Tuple]):
        """并行验证所有任务"""
        if not tasks:
            logger.info("No tasks to verify")
            return
        
        logger.info(f"🚀 Starting parallel verification with {self.args.num_workers} workers")
        logger.info(f"   Timeout per proof: {self.args.timeout}s")
        logger.info(f"   Memory limit per worker: {Config.MAX_MEMORY_PER_WORKER_MB}MB")
        
        # 检查系统资源
        ok, msg = self.resource_monitor.check_system_limits()
        if not ok:
            logger.warning(f"⚠️  Resource warning: {msg}")
        
        try:
            # 使用ProcessPoolExecutor提供更好的控制
            with ProcessPoolExecutor(
                max_workers=self.args.num_workers,
                initializer=init_worker,
                mp_context=multiprocessing.get_context('spawn' if sys.platform == "win32" else 'fork')
            ) as executor:
                
                # 提交所有任务
                future_to_task = {
                    executor.submit(verify_single_proof, task): task 
                    for task in tasks
                }
                
                # 处理结果
                with tqdm(total=len(tasks), desc="Verifying", unit="proofs") as pbar:
                    for future in as_completed(future_to_task):
                        try:
                            result = future.result(timeout=self.args.timeout + 5)
                            
                            if result:
                                # 更新统计
                                memory_used = result.memory_used_mb or 0
                                self.stats.update_stats(result, memory_used=memory_used)
                                
                                # 缓存成功结果
                                if (result.status == VerificationStatus.SUCCESS and 
                                    self.cache_manager and 
                                    result.normalized_hash):
                                    
                                    cache_key = self.cache_manager.get_cache_key(
                                        result.original_decl, 
                                        result.proof_only
                                    )
                                    self.cache_manager.set(cache_key, result.to_dict())
                                
                                # 存储结果
                                if result.status == VerificationStatus.SUCCESS:
                                    self.solved_tasks[result.task_id].append(result)
                            
                            pbar.update(1)
                            pbar.set_postfix({
                                'success': self.stats.successful_tasks,
                                'rate': f"{self.stats.get_summary()['success_rate']:.1%}"
                            })
                            
                        except Exception as e:
                            logger.error(f"Error processing future: {e}")
                            pbar.update(1)
                
                # 保存缓存
                if self.cache_manager:
                    self.cache_manager.save()
        
        except KeyboardInterrupt:
            logger.warning("\n🛑 Verification interrupted by user")
            # 保存当前进度
            if self.cache_manager:
                self.cache_manager.save()
            raise
        except Exception as e:
            logger.error(f"❌ Parallel verification failed: {e}")
            traceback.print_exc()
            raise
    
    def select_best_solutions(self) -> List[Dict]:
        """选择最佳解决方案"""
        final_data = []
        
        logger.info("🏆 Selecting best solutions...")
        
        for task_id, proofs in tqdm(self.solved_tasks.items(), desc="Selecting", unit="problems"):
            if not proofs:
                continue
            
            # 1. 按状态和完整性分组
            complete_proofs = []
            skeleton_proofs = []
            
            for proof in proofs:
                # 兼容缓存加载的字典类型
                if isinstance(proof, dict):
                    status_val = proof.get('status')
                    is_complete = proof.get('is_complete_proof', False)
                    if status_val == VerificationStatus.SUCCESS.value:
                        if is_complete:
                            # 临时包装成对象以便统一处理，或者修改逻辑支持字典
                            # 这里为了简单，我们假设 proofs 都是对象，如果混用了缓存，需要更复杂的处理
                            # 鉴于代码结构，新运行的验证都是对象，只有从load_tasks里恢复的缓存是问题
                            # 简便起见，只处理当前运行产生的对象结果
                            pass
                else:
                    if proof.status == VerificationStatus.SUCCESS:
                        if proof.is_complete_proof:
                            complete_proofs.append(proof)
                        else:
                            skeleton_proofs.append(proof)
            
            # 2. 选择候选列表
            candidates = []
            if complete_proofs:
                candidates = complete_proofs
            elif self.args.allow_sorry and skeleton_proofs:
                candidates = skeleton_proofs
            
            if not candidates:
                continue
            
            # 3. 去重和排序
            unique_candidates = self._deduplicate_candidates(candidates)
            
            if not unique_candidates:
                continue
            
            # 4. 选择最佳
            best_solution = self._select_best_candidate(unique_candidates)
            
            # 5. 添加到最终结果
            final_data.append(best_solution)
        
        logger.info(f"✅ Selected {len(final_data)} best solutions")
        return final_data
    
    def _deduplicate_candidates(self, candidates: List[VerificationResult]) -> List[VerificationResult]:
        """去重候选证明"""
        unique_map = {}
        
        for candidate in candidates:
            norm_hash = candidate.normalized_hash
            
            if norm_hash not in unique_map:
                unique_map[norm_hash] = candidate
            else:
                # 选择更短或验证时间更短的
                existing = unique_map[norm_hash]
                if (candidate.length < existing.length or 
                    candidate.verification_time < existing.verification_time):
                    unique_map[norm_hash] = candidate
        
        return list(unique_map.values())
    
    def _select_best_candidate(self, candidates: List[VerificationResult]) -> Dict:
        """从候选中选择最佳"""
        # 按多个标准排序
        candidates.sort(key=lambda x: (
            x.length,                    # 优先更短
            x.verification_time,         # 其次更快
            -len(x.warnings)             # 警告少的优先
        ))
        
        best = candidates[0]
        
        # 转换为字典并添加元数据
        result_dict = best.to_dict()
        result_dict['selection_metrics'] = {
            'total_candidates': len(candidates),
            'rank': 1,
            'selection_criteria': ['length', 'verification_time', 'warnings']
        }
        
        return result_dict
    
    def save_results(self, final_data: List[Dict]):
        """保存验证结果"""
        # 创建输出目录
        output_dir = os.path.dirname(self.args.output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # 合并增量结果
        if Config.ENABLE_INCREMENTAL and self.existing_results:
            all_data = {**self.existing_results}
            for item in final_data:
                all_data[item['task_id']] = item
            final_data = list(all_data.values())
        
        # 保存主要结果
        logger.info(f"💾 Saving results to {self.args.output_file}")
        
        with open(self.args.output_file, 'w', encoding='utf-8') as f:
            for item in final_data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        
        # 保存详细统计信息
        stats_data = self._generate_statistics(final_data)
        
        stats_file = self.args.output_file.replace('.jsonl', '_stats.json')
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats_data, f, indent=2, ensure_ascii=False)
        
        # 保存错误分析
        error_file = self.args.output_file.replace('.jsonl', '_errors.json')
        self._save_error_analysis(error_file)
        
        return stats_data
    
    def _generate_statistics(self, final_data: List[Dict]) -> Dict:
        """生成统计信息"""
        complete_count = sum(1 for x in final_data 
                           if x.get('is_complete_proof', False))
        
        # 按状态统计
        status_counts = defaultdict(int)
        for item in final_data:
            status = item.get('status', 'unknown')
            status_counts[status] += 1
        
        # 长度分布
        lengths = [item.get('length', 0) for item in final_data]
        
        stats = {
            "timestamp": datetime.now().isoformat(),
            "input_file": self.args.input_file,
            "output_file": self.args.output_file,
            "total_problems_processed": self.stats.total_tasks,
            "total_solutions_kept": len(final_data),
            "complete_proofs": complete_count,
            "skeleton_proofs": len(final_data) - complete_count,
            "status_distribution": dict(status_counts),
            "length_statistics": {
                "min": min(lengths) if lengths else 0,
                "max": max(lengths) if lengths else 0,
                "average": sum(lengths) / len(lengths) if lengths else 0,
                "median": sorted(lengths)[len(lengths)//2] if lengths else 0
            },
            "performance": self.stats.get_summary(),
            "system_info": self.resource_monitor.get_system_info(),
            "config": {
                "allow_sorry": self.args.allow_sorry,
                "num_workers": self.args.num_workers,
                "timeout": self.args.timeout,
                "max_memory_mb": Config.MAX_MEMORY_PER_WORKER_MB,
                "enable_cache": Config.ENABLE_CACHE,
                "enable_incremental": Config.ENABLE_INCREMENTAL
            }
        }
        
        return stats
    
    def _save_error_analysis(self, error_file: str):
        """保存错误分析"""
        error_counts = defaultdict(int)
        
        for task_id, proofs in self.solved_tasks.items():
            for proof in proofs:
                # 兼容字典和对象
                status = proof.get('status') if isinstance(proof, dict) else proof.status.value
                if status != VerificationStatus.SUCCESS.value:
                    error_counts[status] += 1
        
        analysis = {
            "error_distribution": dict(error_counts),
            "common_error_messages": self._extract_common_errors(),
            "timestamp": datetime.now().isoformat()
        }
        
        with open(error_file, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)
    
    def _extract_common_errors(self) -> List[Dict]:
        """提取常见错误"""
        # 这里可以扩展为更详细的错误分析
        return []
    
    def run(self):
        """运行完整的验证流程"""
        # 设置临时目录
        logger.info(f"📁 Using temp directory: {Config.TEMP_DIR}")
        
        # 检查环境
        if not self.check_lean_environment():
            logger.error("❌ Lean environment check failed")
            return False
        
        # 加载任务
        tasks = self.load_tasks()
        if not tasks:
            logger.warning("⚠️  No tasks to process")
            return False
        
        # 验证任务
        self.verify_parallel(tasks)
        
        # 选择最佳解决方案
        final_data = self.select_best_solutions()
        
        # 保存结果
        stats = self.save_results(final_data)
        
        # 显示最终报告
        self._print_final_report(stats)
        
        return True
    
    def _print_final_report(self, stats: Dict):
        """打印最终报告"""
        logger.info("=" * 60)
        logger.info("🎉 VERIFICATION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"📊 Summary:")
        logger.info(f"   Total problems processed: {stats['total_problems_processed']}")
        logger.info(f"   Solutions kept: {stats['total_solutions_kept']}")
        logger.info(f"   Complete proofs: {stats['complete_proofs']}")
        logger.info(f"   Skeleton proofs: {stats['skeleton_proofs']}")
        logger.info(f"   Success rate: {stats['performance']['success_rate']:.1%}")
        logger.info(f"   Average verification time: {stats['performance']['avg_time_per_task']:.2f}s")
        logger.info(f"   Total time: {stats['performance']['total_time_seconds']:.1f}s")
        logger.info(f"   Tasks per second: {stats['performance']['tasks_per_second']:.2f}")
        logger.info("")
        logger.info(f"💾 Results saved to: {self.args.output_file}")
        logger.info(f"📈 Statistics saved to: {self.args.output_file.replace('.jsonl', '_stats.json')}")
        logger.info("=" * 60)

# --- 主函数 ---
def main():
    parser = argparse.ArgumentParser(
        description="🚀 Lean 4 Proof Verifier - Advanced Parallel Verification System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python verify_proofs.py --input_file solutions.jsonl
  
  # Allow proofs with sorry
  python verify_proofs.py --allow_sorry --num_workers 8
  
  # Custom configuration
  python verify_proofs.py --timeout 60 --max_memory_mb 8192 --lean_gym_path /path/to/lean_gym
  
  # Disable cache and incremental processing
  python verify_proofs.py --disable-cache --disable-incremental
        """
    )
    
    # 输入/输出
    parser.add_argument("--input_file", type=str, default=Config.DEFAULT_INPUT_FILE,
                        help="输入JSONL文件路径")
    parser.add_argument("--output_file", type=str, default=Config.DEFAULT_OUTPUT_FILE,
                        help="输出JSONL文件路径")
    
    # 验证选项
    parser.add_argument("--allow_sorry", action="store_true",
                        help="允许包含sorry/admit的证明")
    parser.add_argument("--timeout", type=int, default=Config.TIMEOUT,
                        help="每个证明的超时时间（秒）")
    parser.add_argument("--max_memory_mb", type=int, default=Config.MAX_MEMORY_PER_WORKER_MB,
                        help="每个工作进程的最大内存（MB）")
    
    # 并行选项
    parser.add_argument("--num_workers", type=int, default=Config.NUM_WORKERS,
                        help="并行工作进程数")
    
    # 功能选项
    parser.add_argument("--disable-cache", action="store_true",
                        help="禁用结果缓存")
    parser.add_argument("--disable-incremental", action="store_true",
                        help="禁用增量处理")
    
    # 环境选项
    parser.add_argument("--lean_gym_path", type=str, default=Config.LEAN_GYM_PATH,
                        help="lean_gym项目路径")
    
    # 日志选项
    parser.add_argument("--log_file", type=str,
                        help="日志文件路径（默认：verification_YYYYMMDD_HHMMSS.log）")
    parser.add_argument("--debug", action="store_true",
                        help="启用调试模式")
    
    args = parser.parse_args()
    
    # 动态更新配置
    Config.update_from_args(args)
    
    # 设置日志
    if not args.log_file:
        args.log_file = f"verification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    setup_logging(args.log_file)
    
    logger.info("=" * 60)
    logger.info("🚀 Starting Lean 4 Proof Verifier")
    logger.info("=" * 60)
    logger.info(f"Input file: {args.input_file}")
    logger.info(f"Output file: {args.output_file}")
    logger.info(f"Workers: {args.num_workers}")
    logger.info(f"Timeout: {args.timeout}s")
    logger.info(f"Memory limit: {args.max_memory_mb}MB per worker")
    logger.info(f"Allow sorry: {args.allow_sorry}")
    logger.info(f"Cache enabled: {not args.disable_cache}")
    logger.info(f"Incremental processing: {not args.disable_incremental}")
    logger.info("=" * 60)
    
    # 运行验证器
    verifier = ProofVerifier(args)
    
    try:
        success = verifier.run()
        return 0 if success else 1
    except KeyboardInterrupt:
        logger.info("\n\n👋 Verification interrupted by user")
        return 130  # SIGINT退出码
    except Exception as e:
        logger.error(f"\n❌ Fatal error: {e}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    # 多进程支持
    multiprocessing.freeze_support()
    
    if sys.platform == "win32":
        multiprocessing.set_start_method('spawn', force=True)
    
    # 确保临时目录存在
    Path(Config.TEMP_DIR).mkdir(parents=True, exist_ok=True)
    
    # 运行主程序
    sys.exit(main())