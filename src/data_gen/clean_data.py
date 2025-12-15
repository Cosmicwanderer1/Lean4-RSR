import json
import os
import shutil

def clean_truncated_data():
    # 配置路径
    data_dir = "./data/synthetic"
    input_file = os.path.join(data_dir, "mathlib_consensus.jsonl")
    output_file = os.path.join(data_dir, "mathlib_consensus_clean.jsonl")
    
    if not os.path.exists(input_file):
        print(f"❌ Input file not found: {input_file}")
        return

    print(f"🧹 Scanning {input_file} for bad data...")
    
    total_lines = 0
    kept_lines = 0
    deleted_lines = 0
    
    reasons = {
        "json_error": 0,
        "target_incomplete": 0,  # 没写完骨架
        "metadata_dirty": 0      # Metadata 里混入了标签（说明是原始文本且可能截断）
    }

    with open(input_file, 'r', encoding='utf-8') as f_in, \
         open(output_file, 'w', encoding='utf-8') as f_out:
        
        for line in f_in:
            total_lines += 1
            is_bad = False
            reason = ""
            
            try:
                data = json.loads(line)
                target = data.get("target", "")
                metadata = data.get("metadata", {})
                
                # -------------------------------------------------
                # 规则 1: 核心产出 (Target) 必须完整
                # -------------------------------------------------
                if "</SKELETON>" not in target:
                    is_bad = True
                    reason = "target_incomplete"
                
                # -------------------------------------------------
                # 规则 2: 中间思考 (Metadata) 必须纯净
                # -------------------------------------------------
                if not is_bad:
                    fwd = metadata.get("forward_thought", "").strip()
                    bwd = metadata.get("backward_thought", "").strip()
                    
                    # 只要是以 TAG 开头的，就说明 reasoners.py 的正则提取失败了
                    # 正常的思考应该是 "The theorem states..." 而不是 "<FORWARD_THOUGHT>..."
                    # 我们检查是否包含标签的前缀 "<FORWARD" 或 "<BACKWARD"
                    
                    if "<FORWARD" in fwd or "<BACKWARD" in bwd:
                        is_bad = True
                        reason = "metadata_dirty"
                        
                    # 双重保险：检查这俩是否为空（有时候截断导致空字符串）
                    if not fwd or not bwd:
                        is_bad = True
                        reason = "metadata_empty"

            except json.JSONDecodeError:
                is_bad = True
                reason = "json_error"
            
            if is_bad:
                deleted_lines += 1
                reasons[reason] = reasons.get(reason, 0) + 1
            else:
                f_out.write(line)
                kept_lines += 1

    print("-" * 30)
    print(f"✅ Cleanup Complete!")
    print(f"   Total lines:   {total_lines}")
    print(f"   Kept lines:    {kept_lines}")
    print(f"   Deleted lines: {deleted_lines}")
    print("-" * 30)
    print("   Deletion Stats:")
    for r, count in reasons.items():
        if count > 0:
            print(f"   - {r}: {count}")
    print("-" * 30)
    
    if kept_lines > 0:
        print(f"💾 Clean data saved to: {output_file}")
        user_input = input("❓ Overwrite original file? (y/n): ")
        if user_input.lower() == 'y':
            shutil.move(output_file, input_file)
            print("✅ File overwritten.")
    else:
        print("⚠️  Warning: 0 lines kept. Please check your data format manually.")

if __name__ == "__main__":
    clean_truncated_data()