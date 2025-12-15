import json
import os
from tqdm import tqdm
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
from src.common.rsr_prompts import format_rsr_input
from src.inference.hammer import LeanHammer

def load_model(config_path="configs/config.yaml"):
    import yaml
    with open(config_path, "r", encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    
    base_id = cfg["model"]["base_model_id"]
    adapter_path = cfg["project"]["output_dir"]
    
    print(f"🚀 Loading Base: {base_id}")
    model = AutoModelForCausalLM.from_pretrained(
        base_id, 
        torch_dtype=torch.float16, 
        device_map="auto",
        trust_remote_code=True
    )
    
    print(f"🔗 Loading LoRA: {adapter_path}")
    model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()
    
    tokenizer = AutoTokenizer.from_pretrained(base_id, trust_remote_code=True)
    return model, tokenizer

def generate_skeleton(model, tokenizer, theorem):
    prompt = format_rsr_input(theorem)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs, 
            max_new_tokens=1024, 
            temperature=0.3
        )
    
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    # 提取 <SKELETON>
    import re
    match = re.search(r"<SKELETON>(.*?)</SKELETON>", response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None

def main():
    # 1. 准备
    model, tokenizer = load_model()
    hammer = LeanHammer()
    
    # 2. 加载测试集 (MiniF2F)
    data_path = "./data/raw/minif2f.jsonl" # 确保您之前下载了
    if not os.path.exists(data_path):
        print("❌ Test data not found. Please download MiniF2F first.")
        return

    results = []
    
    # 3. 循环测试
    with open(data_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()[:50] # 先测前50个
        
    print(f"🧪 Evaluating on {len(lines)} problems...")
    
    for i, line in enumerate(tqdm(lines)):
        data = json.loads(line)
        theorem = data.get('formal_statement')
        if not theorem: continue
        
        # A. 生成骨架
        skeleton = generate_skeleton(model, tokenizer, theorem)
        
        if not skeleton:
            results.append({"id": i, "status": "failed_gen"})
            continue
            
        # B. 填补 sorry
        proof_code = hammer.equip_skeleton(skeleton)
        
        # C. 验证
        verify_res = hammer.verify(proof_code, filename=f"Eval_{i}.lean")
        
        results.append({
            "id": i,
            "theorem": theorem,
            "skeleton": skeleton,
            "passed": verify_res["passed"],
            "error": verify_res["error"]
        })
        
    # 4. 统计
    passed = len([r for r in results if r["passed"]])
    print(f"\n🏆 Pass@1: {passed}/{len(lines)} ({passed/len(lines)*100:.1f}%)")
    
    # 保存结果
    os.makedirs("./outputs/eval", exist_ok=True)
    with open("./outputs/eval/results.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()