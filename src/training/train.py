import yaml
import torch
import os
from datasets import load_dataset
from peft import LoraConfig, prepare_model_for_kbit_training, get_peft_model
from transformers import (
    AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
)
from trl import SFTTrainer
from src.common.rsr_prompts import format_rsr_input

def load_config():
    # 确保读取正确的文件
    config_path = "configs/config.yaml"
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")
    with open(config_path, "r", encoding='utf-8') as f:
        return yaml.safe_load(f)

def formatting_func(example):
    """
    将数据转换为 Qwen/ChatML 格式
    """
    output_texts = []
    
    inputs = example['input']
    targets = example['target']
    
    if isinstance(inputs, str):
        inputs = [inputs]
        targets = [targets]
    
    for i in range(len(inputs)):
        if not inputs[i]:
            continue
            
        prompt = format_rsr_input(inputs[i])
        target_str = str(targets[i]) if targets[i] is not None else ""
        # 加上 EOS token 确保模型知道什么时候停止
        text = prompt + target_str + "<|im_end|>"
        output_texts.append(text)
        
    return output_texts

def main():
    cfg = load_config()
    model_id = cfg["model"]["base_model_id"]
    output_dir = cfg["project"]["output_dir"]
    data_path = cfg["data"]["synthetic_path"]
    
    # 1. 检测硬件支持，优先使用 BF16 (RTX 30/40系列专用)
    # BF16 比 FP16 训练更稳定，不易溢出
    use_bf16 = torch.cuda.is_bf16_supported()
    compute_dtype = torch.bfloat16 if use_bf16 else torch.float16
    
    print(f"🚀 Starting training pipeline (Pro Mode)...")
    print(f"   Base Model: {model_id}")
    print(f"   Compute Dtype: {compute_dtype}")
    print(f"   Max Length: {cfg['data']['max_length']}")

    # 2. 量化配置
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=cfg["training"]["use_4bit"],
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype, # 这里联动修改
        bnb_4bit_use_double_quant=True
    )

    # 3. 加载模型
    model = AutoModelForCausalLM.from_pretrained(
        model_id, 
        quantization_config=bnb_config, 
        device_map="auto",
        trust_remote_code=True,
        # 显式指定注意力实现，SDPA 是 PyTorch 2.0+ 原生加速，省显存
        attn_implementation="sdpa" 
    )

    # 开启梯度检查点 (Gradient Checkpointing) - 7B模型跑长文本必开！
    model.gradient_checkpointing_enable()
    model.config.use_cache = False # 训练时必须关闭 KV Cache
    
    model = prepare_model_for_kbit_training(model)
    
    # 加载 Tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right" # SFT 训练通常右侧 padding

    # 4. LoRA 配置
    # 从 config 中动态读取 target_modules，不再硬编码
    target_modules = cfg["training"].get("lora_target_modules", ["q_proj", "v_proj"])
    
    peft_config = LoraConfig(
        r=cfg["training"]["lora_r"],
        lora_alpha=cfg["training"]["lora_alpha"],
        lora_dropout=cfg["training"].get("lora_dropout", 0.05),
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=target_modules, 
    )
    
    print(f"   LoRA Config: r={peft_config.r}, targets={peft_config.target_modules}")

    # 5. 加载数据
    dataset = load_dataset("json", data_files=data_path, split="train")
    print(f"✅ Loaded {len(dataset)} training samples.")

    # 6. 配置训练参数
    training_args = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=cfg["training"]["batch_size"],
        gradient_accumulation_steps=cfg["training"]["grad_accumulation"],
        learning_rate=float(cfg["training"]["learning_rate"]),
        num_train_epochs=cfg["training"]["num_epochs"],
        
        # === 精度与优化 ===
        bf16=use_bf16,        # RTX 4090 开启 BF16
        fp16=not use_bf16,    # 旧卡开启 FP16
        gradient_checkpointing=True, # 【关键】必须开启，否则爆显存
        optim="paged_adamw_32bit",   # 使用分页优化器，进一步节省显存
        
        logging_steps=1,
        save_strategy="epoch",
        warmup_ratio=0.03,
        report_to=["tensorboard"], # 去掉 wandb 避免没配置报错，只有 TensorBoard 也可以
        run_name=cfg["project"]["name"],
        remove_unused_columns=True, 
    )

    # 7. Trainer
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        peft_config=peft_config,
        formatting_func=formatting_func,
        tokenizer=tokenizer,
        args=training_args,
        max_seq_length=cfg["data"]["max_length"],
        packing=False
    )

    print("🔥 Starting training...")
    trainer.train()
    
    print(f"💾 Saving model to {output_dir}")
    trainer.model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print("🎉 Training Complete!")

if __name__ == "__main__":
    main()