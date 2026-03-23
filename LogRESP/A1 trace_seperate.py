import os
import shutil
import concurrent.futures
import time

# --- 1. Configuration ---
SOURCE_DIR = r"C:\Users\Student\Downloads\Theia Complete\theia"
BASE_DEST_DIR = r"C:\Users\Student\Downloads\Theia_E5_Prototype_Files"

# Using the actual existing files from official-2
DATA_SPLITS = {
    "Training": [1, 2, 3, 4, 5],
    "Validation": [15, 16, 17, 18, 19],
    "Testing": [35, 36, 37, 38, 39]  # The late-stage files for this sequence
}

# UPDATED PREFIX: Now pointing to official-2
FILE_PREFIX = "ta1-theia-1-e5-official-2.bin."
FILE_SUFFIX = ".gz"

# --- 2. The Worker ---
def copy_file_to_split(file_number, split_name):
    filename = f"{FILE_PREFIX}{file_number}{FILE_SUFFIX}"
    src_path = os.path.join(SOURCE_DIR, filename)
    
    dest_folder = os.path.join(BASE_DEST_DIR, split_name)
    dest_path = os.path.join(dest_folder, filename)
    
    if not os.path.exists(src_path):
        return f"[-] Missing: {filename} not found!"
        
    try:
        shutil.copy2(src_path, dest_path)
        return f"[+] Success: Copied {filename} -> {split_name}/"
    except Exception as e:
        return f"[-] Error copying {filename}: {e}"

# --- 3. Orchestrator ---
if __name__ == "__main__":
    print("=== LogMEND Corrected Theia Organizer ===")
    start_time = time.time()
    
    for split_name in DATA_SPLITS.keys():
        os.makedirs(os.path.join(BASE_DEST_DIR, split_name), exist_ok=True)
        
    copy_tasks = [(num, split) for split, nums in DATA_SPLITS.items() for num in nums]
            
    print(f"[*] Copying {len(copy_tasks)} files using SSD Threading...\n")

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        futures = [executor.submit(copy_file_to_split, num, split) for num, split in copy_tasks]
        for future in concurrent.futures.as_completed(futures):
            print(future.result())

    print(f"\n=== THEIA ORGANIZATION COMPLETE ===")
    print(f"Time: {round(time.time() - start_time, 2)}s.")