import json
import random
import time
import os
import ast
from logresp_agent import logresp_app  

# --- 1. Configuration ---
DATASET_PATH = r"C:\Users\Student\Downloads\FINAL_DATASETS\BETH_final_dataset\beth_testing.json"
SAMPLE_SIZE_PER_CLASS = 20  

def load_balanced_dataset(filepath, sample_size):
    """Reads the JSON file and extracts a balanced mix of Benign and Malicious logs."""
    benign_logs = []
    malicious_logs = []
    
    print(f"[*] Reading dataset from {filepath}...")
    
    if not os.path.exists(filepath):
        print(f"[!] ERROR: Cannot find file at {filepath}")
        return []
        
    file_size = os.path.getsize(filepath)
    print(f"[*] File size: {file_size / 1024 / 1024:.2f} MB")
    
    if file_size == 0:
        print("\n[!] CRITICAL ERROR: Your beth_testing.json file is empty!")
        return []

    print("    -> Loading multi-line JSON into memory (This takes a few seconds)...")
    
    # READ THE ENTIRE FILE AT ONCE TO BYPASS MULTI-LINE FORMATTING ISSUES
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        file_content = f.read()

    logs = []
    
    try:
        # 1. Try standard JSON Array parsing [ {...}, {...} ]
        logs = json.loads(file_content)
    except json.JSONDecodeError:
        print("    -> Standard array failed. Attempting consecutive multi-line JSON parsing...")
        try:
            # 2. Try parsing consecutive objects (e.g. {...} \n\n {...})
            decoder = json.JSONDecoder()
            pos = 0
            file_content = file_content.lstrip()
            while pos < len(file_content):
                obj, index = decoder.raw_decode(file_content, pos)
                logs.append(obj)
                pos = index
                while pos < len(file_content) and file_content[pos].isspace():
                    pos += 1
        except Exception:
            try:
                # 3. Sledgehammer fallback for single-quoted Python dictionaries
                logs = ast.literal_eval(file_content)
            except Exception as e:
                print(f"[!] Critical Error parsing file format: {e}")
                return []

    if not isinstance(logs, list):
        print("[!] Error: The parsed data is not a list of logs.")
        return []

    # Sort the successfully loaded logs
    for log in logs:
        if isinstance(log, dict):
            is_evil = int(log.get("is_evil", 0))
            if is_evil == 1:
                malicious_logs.append(log)
            else:
                benign_logs.append(log)

    print(f"    -> Successfully loaded {len(benign_logs)} Benign and {len(malicious_logs)} Malicious logs.")
    
    if len(benign_logs) == 0 and len(malicious_logs) == 0:
        return []
    
    # Sample the logs securely
    sampled_benign = random.sample(benign_logs, min(sample_size, len(benign_logs)))
    sampled_malicious = random.sample(malicious_logs, min(sample_size, len(malicious_logs)))
    
    combined_test_set = sampled_benign + sampled_malicious
    random.shuffle(combined_test_set) 
    
    return combined_test_set

def evaluate_pipeline():
    test_logs = load_balanced_dataset(DATASET_PATH, SAMPLE_SIZE_PER_CLASS)
    
    if not test_logs:
        print("\n[-] Evaluation aborted because no logs were loaded.")
        return
        
    print(f"\n[*] Starting Blind Evaluation on {len(test_logs)} total logs...")
    
    # Metrics Tracking
    TP, TN, FP, FN = 0, 0, 0, 0
    start_time = time.time()
    
    for i, log in enumerate(test_logs, 1):
        actual_is_evil = log.get("is_evil", 0)
        actual_label = "Malicious" if actual_is_evil == 1 else "Benign"
        
        initial_state = {
            "raw_log": log,
            "process_id": str(log.get("process_id", "UNKNOWN")),
            "neo4j_context": "",
            "final_analysis": ""
        }
        
        print(f"\n[Test {i}/{len(test_logs)}] Analyzing Process {log.get('process_id')} (Ground Truth: {actual_label})")
        
        try:
            result = logresp_app.invoke(initial_state)
            ai_analysis = result["final_analysis"].lower()
            
            # Grade the response
            ai_predicted_malicious = "malicious" in ai_analysis and "benign" not in ai_analysis
            
            if actual_is_evil == 1:
                if ai_predicted_malicious:
                    TP += 1
                    print("    -> ✅ TRUE POSITIVE (AI Caught the Attack!)")
                else:
                    FN += 1
                    print("    -> ❌ FALSE NEGATIVE (AI Missed the Attack!)")
            else:
                if ai_predicted_malicious:
                    FP += 1
                    print("    -> ❌ FALSE POSITIVE (AI Hallucinated an Attack!)")
                else:
                    TN += 1
                    print("    -> ✅ TRUE NEGATIVE (AI Correctly Ignored Normalcy)")
                    
        except Exception as e:
            print(f"    -> ⚠️ ERROR analyzing log: {e}")

    # --- CALCULATE FINAL RESEARCH METRICS ---
    duration = round(time.time() - start_time, 2)
    
    precision = TP / (TP + FP) if (TP + FP) > 0 else 0.0
    recall = TP / (TP + FN) if (TP + FN) > 0 else 0.0
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (TP + TN) / len(test_logs) if len(test_logs) > 0 else 0.0

    print("\n" + "="*50)
    print("🏆 FINAL LogRESP RESEARCH METRICS 🏆")
    print("="*50)
    print(f"Total Logs Tested: {len(test_logs)}")
    print(f"Time Taken:        {duration} seconds")
    print("-" * 30)
    print(f"True Positives (TP):  {TP}")
    print(f"True Negatives (TN):  {TN}")
    print(f"False Positives (FP): {FP}")
    print(f"False Negatives (FN): {FN}")
    print("-" * 30)
    print(f"🎯 ACCURACY:  {accuracy * 100:.2f}%")
    print(f"🎯 PRECISION: {precision * 100:.2f}%")
    print(f"🎯 RECALL:    {recall * 100:.2f}%")
    print(f"🎯 F1-SCORE:  {f1_score * 100:.2f}%")
    print("="*50)

if __name__ == "__main__":
    evaluate_pipeline()