import fastavro
import gzip
import json
import os
import time
import concurrent.futures

# --- 1. Configuration ---
# Pointing to the Theia folders you just successfully created!
PROTOTYPE_DIR = r"C:\Users\Student\Downloads\Theia_E5_Prototype_Files"
OUTPUT_DIR = r"C:\Users\Student\Downloads\LogMEND_Theia_Splits"

# Utilize your powerful CPU cores
MAX_CORES = max(1, os.cpu_count() - 4)

# Grabbing ONLY the actions an APT uses (Process, Network, File modification)
HIGH_VALUE_EVENTS = {
    'EVENT_EXECUTE', 'EVENT_FORK', 'EVENT_CLONE', 
    'EVENT_CONNECT', 'EVENT_ACCEPT', 'EVENT_SENDTO', 'EVENT_RECVFROM',
    'EVENT_OPEN', 'EVENT_WRITE', 'EVENT_MODIFY_FILE_ATTRIBUTES'
}

def byte_to_string_handler(obj):
    """Translates DARPA's raw binary hashes into readable text strings."""
    if isinstance(obj, bytes):
        try: return obj.decode('utf-8')
        except UnicodeDecodeError: return obj.hex()
    return obj

def extract_cdm20_features(record):
    """Parses the nested 'datum' structure for Theia."""
    if record.get('type') != 'RECORD_EVENT':
        return None
        
    datum = record.get('datum', {})
    event_type = datum.get('type', '')
    
    # Drop the noise (background memory allocation, etc.)
    if event_type not in HIGH_VALUE_EVENTS:
        return None
        
    properties = datum.get('properties', {})
    
    # Build the clean, flat JSON dictionary for your LangGraph Agents
    clean_log = {
        "timestamp_ns": datum.get('timestampNanos', 0),
        "event_type": event_type,
        "thread_id": datum.get('threadId', 'UNKNOWN'),
        "cmdLine": properties.get('cmdLine', None),
        "file_path": datum.get('predicateObjectPath', None),
        "remote_ip": properties.get('remoteAddress', None),
        "remote_port": properties.get('remotePort', None)
    }
    
    # Remove any empty fields to save LLM context space
    return {k: v for k, v in clean_log.items() if v is not None}

def process_file_in_ram(filepath):
    """Worker function: Runs on a single CPU core to parse one Theia .gz file."""
    filename = os.path.basename(filepath)
    extracted_logs = []
    
    try:
        with gzip.open(filepath, 'rb') as f_in:
            reader = fastavro.reader(f_in)
            for record in reader:
                clean_log = extract_cdm20_features(record)
                if clean_log:
                    # Clean the bytes and format as a standard JSON string
                    safe_log = {k: byte_to_string_handler(v) for k, v in clean_log.items()}
                    extracted_logs.append(json.dumps(safe_log))
                    
        return filename, extracted_logs, None
    except Exception as e:
        return filename, [], str(e)

def process_split(split_name):
    """Orchestrates the extraction for a specific folder (e.g., 'Testing')."""
    folder_path = os.path.join(PROTOTYPE_DIR, split_name)
    output_filepath = os.path.join(OUTPUT_DIR, f"theia_{split_name.lower()}.json")
    
    if not os.path.exists(folder_path):
        print(f"[-] Folder not found: {folder_path}")
        return

    files = sorted([os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith(".gz")])
    if not files:
        print(f"[-] No .gz files found in {split_name} folder.")
        return

    print(f"\n[*] Mining {split_name} Set ({len(files)} files) using {MAX_CORES} CPU Cores...")
    start_time = time.time()
    total_extracted = 0
    
    with open(output_filepath, 'w', encoding='utf-8') as f_out:
        # Fire up the multi-processing pool
        with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_CORES) as executor:
            results = executor.map(process_file_in_ram, files)
            
            # Write extracted JSON logs to the final file
            for filename, logs, error in results:
                if error:
                    print(f"      [-] Error processing {filename}: {error}")
                else:
                    for log in logs:
                        f_out.write(log + '\n')
                    total_extracted += len(logs)
                    print(f"      [+] {filename} -> Extracted {len(logs)} high-value JSON logs.")
                    
    duration = round(time.time() - start_time, 2)
    print(f"    [=] {split_name} Complete: {total_extracted} clean JSON logs extracted in {duration}s.")

if __name__ == "__main__":
    # Create the output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=== LogMEND Theia JSON Extractor Initiated ===")
    
    # Process all three folders
    process_split("Training")
    process_split("Validation")
    process_split("Testing")
    
    print(f"\n=== EXTRACTION COMPLETE ===")
    print(f"Your clean Theia JSON datasets are ready at: {OUTPUT_DIR}")