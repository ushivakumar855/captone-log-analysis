import csv
import json
import os
import time

# --- 1. Configuration ---
# Paths mapped exactly to your Windows environment
BETH_DIR = r"C:\Users\Student\Downloads\BETH dataset"
OUTPUT_DIR = r"C:\Users\Student\Downloads\LogMEND_BETH_Splits"

# The 3 specific pre-segregated files we need
TARGET_FILES = {
    "Training": "labelled_training_data.csv",
    "Validation": "labelled_validation_data.csv",
    "Testing": "labelled_testing_data.csv"
}

def translate_beth_to_logmend(row):
    """
    Translates BETH's CSV columns into the unified JSON schema.
    We map BETH's 'processName' to 'cmdLine' so the AI treats it exactly like Trace/Theia.
    """
    try:
        clean_log = {
            "timestamp": float(row.get("timestamp", 0)),
            "event_type": row.get("eventName", "UNKNOWN"),
            "thread_id": row.get("threadId", None),
            "process_id": row.get("processId", None),
            "parent_process_id": row.get("parentProcessId", None),
            "cmdLine": row.get("processName", None), # Mapped for unified AI ingestion
            "user_id": row.get("userId", None),
            "return_value": row.get("returnValue", None),
            # Ground truth labels required for evaluation
            "is_suspicious": int(row.get("sus", 0)),
            "is_evil": int(row.get("evil", 0))
        }
        
        # Remove empty/null fields to save context space
        return {k: v for k, v in clean_log.items() if v not in [None, '', ' ']}
    except Exception:
        return None

def process_csv(split_name, filename):
    input_path = os.path.join(BETH_DIR, filename)
    output_path = os.path.join(OUTPUT_DIR, f"beth_{split_name.lower()}.json")
    
    if not os.path.exists(input_path):
        print(f"[-] Missing: {filename} not found in {BETH_DIR}")
        return

    print(f"[*] Translating {split_name} Set ({filename})...")
    start_time = time.time()
    count = 0
    
    # Read the CSV and stream it to a JSONL file
    with open(input_path, mode='r', encoding='utf-8') as csv_file:
        csv_reader = csv.DictReader(csv_file)
        
        with open(output_path, mode='w', encoding='utf-8') as json_out:
            for row in csv_reader:
                json_log = translate_beth_to_logmend(row)
                if json_log:
                    json_out.write(json.dumps(json_log) + '\n')
                    count += 1
                    
    duration = round(time.time() - start_time, 2)
    print(f"    [+] Success! Converted {count} logs to JSONL in {duration}s.")

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=== LogMEND BETH CSV-to-JSON Universal Adapter ===")
    
    for split, filename in TARGET_FILES.items():
        process_csv(split, filename)
        
    print("\n=== ADAPTER COMPLETE ===")
    print(f"Your unified BETH data is ready at: {OUTPUT_DIR}")