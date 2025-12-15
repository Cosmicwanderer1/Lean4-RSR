import json
import os
import torch
from tqdm import tqdm
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

def main():
    # Configuration
    # Base model from HuggingFace (or local cache)
    base_model_name = "Qwen/Qwen2.5-Math-7B-Instruct"
    # Path to your LoRA adapter
    lora_path = "models/math-thinker-7b-pro/strategist-lora-mathlib-7b-pro"
    
    input_file = "data/raw/mathlib_10k_prompts.jsonl"
    output_file = "data/processed/mathlib_10k_solutions.jsonl"
    
    # Generation parameters
    num_samples = 32      # Number of solutions per problem
    temperature = 0.7     # Creativity
    max_new_tokens = 1024 # Max length of the proof
    
    # Check for GPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")

    # 1. Load Tokenizer
    print(f"Loading tokenizer from {lora_path}...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(lora_path, trust_remote_code=True)
    except:
        print(f"Fallback: Loading tokenizer from {base_model_name}...")
        tokenizer = AutoTokenizer.from_pretrained(base_model_name, trust_remote_code=True)

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    # 2. Load Model
    print(f"Loading base model {base_model_name}...")
    model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        device_map="auto",
        torch_dtype=torch.float16, # Use bfloat16 if on Ampere+ GPUs
        trust_remote_code=True
    )
    
    print(f"Loading LoRA adapter from {lora_path}...")
    model = PeftModel.from_pretrained(model, lora_path)
    model.eval()

    # 3. Prepare Output & Resume Logic
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    processed_ids = set()
    if os.path.exists(output_file):
        print(f"Found existing output file. Scanning for processed tasks...")
        with open(output_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if 'task_id' in data:
                        processed_ids.add(data['task_id'])
                except:
                    continue
        print(f"Resuming... {len(processed_ids)} tasks already processed.")

    # 4. Load Prompts
    prompts = []
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                item = json.loads(line)
                if item['task_id'] not in processed_ids:
                    prompts.append(item)
            except:
                continue

    print(f"Loaded {len(prompts)} new tasks to process.")

    # 5. Generation Loop
    # We open in 'a' (append) mode to save progress incrementally
    with open(output_file, 'a', encoding='utf-8') as f_out:
        for item in tqdm(prompts, desc="Generating Solutions"):
            prompt_text = item['prompt']
            
            # Tokenize
            inputs = tokenizer(prompt_text, return_tensors="pt").to(model.device)
            
            try:
                with torch.no_grad():
                    # Generate multiple samples
                    # Note: Generating 32 sequences at once might OOM on smaller cards.
                    # If OOM occurs, reduce num_return_sequences and run in a loop.
                    outputs = model.generate(
                        **inputs,
                        max_new_tokens=max_new_tokens,
                        num_return_sequences=num_samples,
                        temperature=temperature,
                        do_sample=True,
                        pad_token_id=tokenizer.pad_token_id,
                        eos_token_id=tokenizer.eos_token_id
                    )
                
                # Decode
                generated_texts = tokenizer.batch_decode(outputs, skip_special_tokens=True)
                
                solutions = []
                for text in generated_texts:
                    # Remove the prompt from the beginning to get just the solution
                    # (Qwen might repeat the prompt)
                    if text.startswith(prompt_text):
                        sol = text[len(prompt_text):]
                    else:
                        sol = text
                    solutions.append(sol.strip())

                # Save result
                result = {
                    "task_id": item['task_id'],
                    "prompt": prompt_text,
                    "solutions": solutions,
                    "original_decl": item.get("original_decl", "")
                }
                
                f_out.write(json.dumps(result, ensure_ascii=False) + "\n")
                f_out.flush()
                
            except RuntimeError as e:
                if "out of memory" in str(e):
                    print(f"OOM Error on task {item['task_id']}. Skipping or try reducing batch size.")
                    torch.cuda.empty_cache()
                else:
                    print(f"Error on task {item['task_id']}: {e}")
                continue
            except Exception as e:
                print(f"Error on task {item['task_id']}: {e}")
                continue

    print("Generation complete!")

if __name__ == "__main__":
    main()
