import subprocess
import os
import re
import tempfile

class LeanHammer:
    """
    Lean 4 '工匠'：负责填补证明骨架中的 sorry
    """
    def __init__(self, project_root="./lean_gym"):
        self.project_root = os.path.abspath(project_root)
        
    def equip_skeleton(self, skeleton_code: str) -> str:
        """
        将骨架中的 'sorry' 替换为自动化策略组合 (Hammers)
        """
        # 定义强力工匠策略
        # aesop: 通用搜索
        # simp_all: 强力化简
        # linarith: 线性算术
        # ring: 环论运算
        hammer_tactic = """
    try
      first
      | aesop
      | simp_all
      | linarith
      | ring
      | norm_num
      | decide
      | sorry -- 如果都失败了，保留 sorry 以便定位
    """
        # 简单替换
        return skeleton_code.replace("sorry", hammer_tactic)

    def verify(self, code: str, filename: str = "HammerTest.lean") -> dict:
        """
        将代码写入文件并调用 Lean 编译器验证
        """
        # 1. 确保引用了 Mathlib
        if "import Mathlib" not in code:
            code = "import Mathlib\n\n" + code

        file_path = os.path.join(self.project_root, filename)
        
        # 2. 写入文件
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)

        # 3. 调用 Lake 编译
        # 命令: lake env lean HammerTest.lean
        cmd = ["lake", "env", "lean", filename]
        
        result = {
            "passed": False,
            "error": None,
            "output": ""
        }

        try:
            process = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60 # 给 Hammer 更多时间
            )
            
            result["output"] = process.stderr
            
            # 4. 判读结果
            # 如果 exit code 为 0，说明没有严重错误
            # 但还需要检查是否有 "error:" 关键词
            if process.returncode == 0:
                # 检查是否还有未完成的 sorry (warning 级别)
                if "warning: declaration uses 'sorry'" in process.stderr:
                    result["passed"] = False # 虽然编译通过，但没证出来
                    result["error"] = "Unsolved goals (sorry)"
                else:
                    result["passed"] = True
            else:
                result["passed"] = False
                result["error"] = process.stderr

        except subprocess.TimeoutExpired:
            result["error"] = "Timeout"
        except Exception as e:
            result["error"] = str(e)

        return result

# 测试
if __name__ == "__main__":
    hammer = LeanHammer()
    
    # 一个简单的测试用例
    test_skeleton = """
    example (a b : Nat) : a + b = b + a := by
      induction a
      sorry
      sorry
    """
    
    print("🔨 Processing skeleton...")
    final_code = hammer.equip_skeleton(test_skeleton)
    print(final_code)
    
    print("\n🔍 Verifying...")
    res = hammer.verify(final_code)
    print(f"Result: {res}")