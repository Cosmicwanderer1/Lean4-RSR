import json
import os
import re
import requests
import zipfile
import io
import glob
from tqdm import tqdm
from typing import List, Dict, Any

# 配置
MATHLIB_URL = "https://github.com/leanprover-community/mathlib4/archive/refs/heads/master.zip"
OUTPUT_DIR = "./data/raw"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "mathlib_theorems.jsonl")
TEMP_DIR = "./data/temp_mathlib"

class MathlibExtractor:
    def __init__(self):
        # 匹配定理声明：更精确的模式，避免重复匹配
        # 使用非贪婪匹配，确保在遇到下一个定义时停止
        self.theorem_pattern = re.compile(
            r"^(?:(protected|private|noncomputable|scoped)\s+)*(theorem|lemma)\s+(\w+)([\s\S]*?):=\s*(by\s+[\s\S]+?)(?=\n(?:theorem|lemma|def|instance|axiom|\Z))",
            re.MULTILINE
        )
        
        self.import_pattern = re.compile(r"^import\s+([\w\.]+)", re.MULTILINE)
        self.open_pattern = re.compile(r"^open\s+([\w\s]+)", re.MULTILINE)

    def download_mathlib(self) -> str:
        """下载并解压 Mathlib4"""
        if os.path.exists(TEMP_DIR):
            # 简单的检查，确保里面有文件
            if len(os.listdir(TEMP_DIR)) > 0:
                print(f"📂 Found existing Mathlib source at {TEMP_DIR}")
                return TEMP_DIR
            
        print(f"⬇️  Downloading Mathlib4 source...")
        try:
            r = requests.get(MATHLIB_URL, stream=True)
            r.raise_for_status()
            z = zipfile.ZipFile(io.BytesIO(r.content))
            print("📦 Extracting zip file...")
            z.extractall("./data")
            
            extracted_folder = os.path.join("./data", z.namelist()[0].split('/')[0])
            if os.path.exists(TEMP_DIR):
                import shutil
                shutil.rmtree(TEMP_DIR)
            os.rename(extracted_folder, TEMP_DIR)
            print(f"✅ Extracted to {TEMP_DIR}")
            return TEMP_DIR
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return ""

    def get_module_name(self, file_path: str, source_root: str) -> str:
        """
        根据文件路径生成 Lean 模块名，用于做唯一 ID。
        例如: ./data/temp_mathlib/Mathlib/Data/Nat/Basic.lean -> Mathlib.Data.Nat.Basic
        """
        rel_path = os.path.relpath(file_path, source_root)
        # 去掉 .lean 后缀
        rel_path = os.path.splitext(rel_path)[0]
        # 将路径分隔符转换为 .
        return rel_path.replace(os.path.sep, ".")

    def process_file(self, file_path: str, source_root: str) -> List[Dict[str, Any]]:
        """处理单个 .lean 文件"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            return []

        # 1. 提取 Imports & Opens
        imports = []
        open_namespaces = []
        
        # 简单的逐行扫描，只扫描前 200 行以提高效率（通常 import/open 都在头部）
        lines = content.split('\n')
        for line in lines[:200]: 
            line = line.strip()
            if line.startswith('import '):
                match = self.import_pattern.match(line)
                if match: imports.append(match.group(1))
            elif line.startswith('open '):
                line = line.split('--')[0].strip()
                match = self.open_pattern.match(line)
                if match:
                    ns_chunk = match.group(1).split()
                    open_namespaces.extend(ns_chunk)

        # 2. 生成模块名作为 ID 前缀
        module_name = self.get_module_name(file_path, source_root)

        # 3. 提取定理
        extracted = []
        matches = self.theorem_pattern.finditer(content)
        
        for m in matches:
            attrs = m.group(1) or ""
            decl_type = m.group(2)
            name = m.group(3)
            signature = m.group(4).strip()
            proof = m.group(5).strip()

            if "private" in attrs: continue
            if "sorry" in proof: continue

            full_statement = f"{decl_type} {name} {signature}"
            
            # 【修复】使用 模块名.定理名 作为唯一ID，解决文件名冲突问题
            unique_id = f"{module_name}.{name}"

            extracted.append({
                "id": unique_id,
                "decl_name": name,
                "module": module_name, # 记录所属模块
                "statement": full_statement,
                "imports": imports,
                "open_namespaces": list(set(open_namespaces)),
                "golden_proof": proof,
                "source_file": file_path
            })
            
        return extracted

    def run(self, max_samples=10000):
        source_dir = self.download_mathlib()
        if not source_dir: return

        lean_files = glob.glob(os.path.join(source_dir, "**/*.lean"), recursive=True)
        print(f"🚀 Found {len(lean_files)} Lean files. Processing...")
        
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # 【断点续传】读取已有数据中的ID
        seen_ids = set()
        if os.path.exists(OUTPUT_FILE):
            print(f"📖 Loading existing IDs for deduplication...")
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        item = json.loads(line)
                        if 'id' in item:
                            seen_ids.add(item['id'])
                    except:
                        continue
            print(f"✅ Found {len(seen_ids)} existing theorems.")
        
        count = len(seen_ids)  # 从已有数量开始计数
        new_count = 0  # 新增的定理数量
        
        # 使用追加模式支持断点续传
        mode = 'a' if os.path.exists(OUTPUT_FILE) and len(seen_ids) > 0 else 'w'
        with open(OUTPUT_FILE, mode, encoding='utf-8') as f_out:
            for file_path in tqdm(lean_files):
                # 传入 source_dir 以计算相对路径
                items = self.process_file(file_path, source_dir)
                
                for item in items:
                    # 【去重】检查 ID 是否已存在
                    if item['id'] in seen_ids:
                        continue
                        
                    seen_ids.add(item['id'])
                    
                    f_out.write(json.dumps(item, ensure_ascii=False) + "\n")
                    f_out.flush()  # 实时刷新，防止数据丢失
                    new_count += 1
                    count += 1
                    
                    if count >= max_samples:
                        break
                
                if count >= max_samples:
                    break
        
        print(f"✅ Extraction complete!")
        print(f"   📊 Total theorems: {count}")
        print(f"   ✨ Newly added: {new_count}")
        print(f"   💾 Saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    extractor = MathlibExtractor()
    extractor.run(max_samples=10000)