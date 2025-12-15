import json
import os
import re
import requests
import zipfile
import io
from tqdm import tqdm
import random


MATHLIB_URL = "https://github.com/leanprover-community/mathlib4/archive/refs/heads/master.zip"

def estimate_difficulty(theorem, proof):
    """
    启发式估计定理难度（简单/中等/困难）
    
    难度判断依据：
    - 简单：证明行数少（<5行），使用基础tactic（simp, rfl, trivial）
    - 中等：中等复杂度（5-15行），包含推理链
    - 困难：长证明（>15行），包含复杂结构（induction, cases, calc）
    """
    proof_lines = [line.strip() for line in proof.split('\n') if line.strip() and not line.strip().startswith('--')]
    line_count = len(proof_lines)
    proof_lower = proof.lower()
    
    # 简单tactic标记
    simple_tactics = ['simp', 'rfl', 'trivial', 'exact', 'assumption', 'refl']
    # 复杂tactic标记
    complex_tactics = ['induction', 'cases', 'calc', 'have', 'suffices', 'obtain', 'rcases']
    
    simple_count = sum(1 for t in simple_tactics if t in proof_lower)
    complex_count = sum(1 for t in complex_tactics if t in proof_lower)
    
    # 判断逻辑
    if line_count <= 4 and simple_count >= 1 and complex_count == 0:
        return 'easy'
    elif line_count > 15 or complex_count >= 2:
        return 'hard'
    else:
        return 'medium'

def extract_theorems_from_code(code_content):
    """
    从 .lean 源代码中启发式地提取 (Theorem, Proof) 对。
    """
    # 匹配 theorem/lemma 的开头，捕获名称和类型声明
    # 这里的正则主要捕获以 'by' 开头的 tactic 证明
    pattern = re.compile(
        r"^(?:protected\s+)?(?:private\s+)?(?:noncomputable\s+)?(?:scoped\s+)?(theorem|lemma)\s+([\s\S]+?):=\s*(by\s+[\s\S]+?)(?=\n\n|\n(?:\S)|$)", 
        re.MULTILINE
    )
    
    extracted = []
    
    try:
        matches = pattern.finditer(code_content)
        for m in matches:
            decl_type = m.group(1) # theorem or lemma
            header = m.group(2).strip()
            proof = m.group(3).strip()
            
            # 过滤掉只有 'sorry' 的证明
            if proof.strip() == "by sorry" or "sorry" in proof:
                continue
                
            # 构造完整的 theorem 声明语句
            full_theorem = f"{decl_type} {header} :="
            
            # 估计难度
            difficulty = estimate_difficulty(full_theorem, proof)
            
            extracted.append({
                "theorem": full_theorem,
                "proof": proof,
                "difficulty": difficulty
            })
    except Exception:
        pass
        
    return extracted

def download_and_extract_mathlib():
    """下载并解压 Mathlib4 源码"""
    temp_dir = "./data/temp_mathlib"
    
    if os.path.exists(temp_dir):
        print(f"📂 Found existing Mathlib source at {temp_dir}, skipping download.")
        return temp_dir
        
    print(f"⬇️  Downloading Mathlib4 source from GitHub...")
    try:
        r = requests.get(MATHLIB_URL, stream=True)
        r.raise_for_status()
        z = zipfile.ZipFile(io.BytesIO(r.content))
        print("📦 Extracting zip file...")
        z.extractall("./data")
        
        # 解压后的文件夹通常叫 mathlib4-master
        extracted_folder = os.path.join("./data", z.namelist()[0].split('/')[0])
        os.rename(extracted_folder, temp_dir)
        print(f"✅ Extracted to {temp_dir}")
        return temp_dir
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return None

def prepare_leandojo_data():
    save_dir = "./data/raw"
    save_path = os.path.join(save_dir, "leandojo_mathlib.jsonl")
    os.makedirs(save_dir, exist_ok=True)
    
    # 目标分布
    TARGET_TOTAL = 1000
    TARGET_EASY = int(TARGET_TOTAL * 0.1)    # 10% = 100道
    TARGET_MEDIUM = int(TARGET_TOTAL * 0.7)  # 70% = 700道
    TARGET_HARD = int(TARGET_TOTAL * 0.2)    # 20% = 200道
    
    print(f"🎯 Target: {TARGET_TOTAL} theorems")
    print(f"   - Easy (10%): {TARGET_EASY}")
    print(f"   - Medium (70%): {TARGET_MEDIUM}")
    print(f"   - Hard (20%): {TARGET_HARD}")
    
    # 1. 获取源码
    source_dir = download_and_extract_mathlib()
    if not source_dir:
        return

    print(f"🚀 Scanning .lean files in {source_dir}...")
    
    # 2. 遍历所有 .lean 文件
    lean_files = []
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            if file.endswith(".lean"):
                lean_files.append(os.path.join(root, file))
    
    print(f"   Found {len(lean_files)} Lean source files.")
    
    # 随机打乱以确保覆盖全部范围
    random.shuffle(lean_files)
    
    print(f"💾 Extracting theorems by difficulty...")
    
    # 按难度分类收集
    theorems_by_difficulty = {
        'easy': [],
        'medium': [],
        'hard': []
    }
    
    # 第一遍：收集所有定理并分类
    for file_path in tqdm(lean_files, desc="Scanning files"):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f_in:
                content = f_in.read()
                
            pairs = extract_theorems_from_code(content)
            
            for p in pairs:
                difficulty = p['difficulty']
                theorems_by_difficulty[difficulty].append({
                    "theorem": p["theorem"],
                    "proof": p["proof"],
                    "difficulty": difficulty,
                    "source": os.path.basename(file_path)
                })
                
        except Exception:
            continue
    
    print(f"\n📊 Collected theorems by difficulty:")
    print(f"   - Easy: {len(theorems_by_difficulty['easy'])}")
    print(f"   - Medium: {len(theorems_by_difficulty['medium'])}")
    print(f"   - Hard: {len(theorems_by_difficulty['hard'])}")
    
    # 第二遍：按目标比例采样
    print(f"\n🎲 Sampling to meet target distribution...")
    
    selected_theorems = []
    
    # 从每个难度级别随机采样
    for difficulty, target_count in [('easy', TARGET_EASY), ('medium', TARGET_MEDIUM), ('hard', TARGET_HARD)]:
        available = theorems_by_difficulty[difficulty]
        
        if len(available) >= target_count:
            # 随机采样
            sampled = random.sample(available, target_count)
        else:
            # 不够就全取，并发出警告
            sampled = available
            print(f"   ⚠️  Only {len(available)} {difficulty} theorems available (target: {target_count})")
        
        selected_theorems.extend(sampled)
        print(f"   ✓ Selected {len(sampled)} {difficulty} theorems")
    
    # 随机打乱最终列表（避免按难度排序）
    random.shuffle(selected_theorems)
    
    # 写入文件
    print(f"\n💾 Saving to {save_path}...")
    with open(save_path, 'w', encoding='utf-8') as f_out:
        for entry in selected_theorems:
            f_out.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    print(f"✅ Successfully extracted {len(selected_theorems)} theorem-proof pairs")
    print(f"   Final distribution:")
    difficulty_counts = {'easy': 0, 'medium': 0, 'hard': 0}
    for t in selected_theorems:
        difficulty_counts[t['difficulty']] += 1
    print(f"   - Easy: {difficulty_counts['easy']} ({difficulty_counts['easy']/len(selected_theorems)*100:.1f}%)")
    print(f"   - Medium: {difficulty_counts['medium']} ({difficulty_counts['medium']/len(selected_theorems)*100:.1f}%)")
    print(f"   - Hard: {difficulty_counts['hard']} ({difficulty_counts['hard']/len(selected_theorems)*100:.1f}%)")
    print("👉 Next step: Run 'python -m src.data_gen.synthesizer'")

if __name__ == "__main__":
    prepare_leandojo_data()