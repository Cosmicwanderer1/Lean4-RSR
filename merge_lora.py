import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import os

def merge_model():
    # --- 配置 ---
    base_model_name = "Qwen/Qwen2.5-Math-7B-Instruct"
    lora_path = "models/math-thinker-7b-pro/strategist-lora-mathlib-7b-pro"
    output_dir = "models/math-thinker-7b-merged"  # 合并后的模型保存路径
    
    print(f"Loading base model: {base_model_name}")
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True
    )
    
    print(f"Loading LoRA adapter: {lora_path}")
    model = PeftModel.from_pretrained(base_model, lora_path)
    
    print("Merging weights...")
    model = model.merge_and_unload() # 关键步骤：融合权重
    
    print(f"Saving merged model to {output_dir}...")
    model.save_pretrained(output_dir)
    
    print("Saving tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(base_model_name, trust_remote_code=True)
    tokenizer.save_pretrained(output_dir)
    
    print("✅ Merge complete! Use this path for vLLM.")

if __name__ == "__main__":
    merge_model()