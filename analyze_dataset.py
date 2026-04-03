import csv
import glob
import os

# Standard schema columns from research
CRITICAL_COLUMNS = ['timestamp', 'processId', 'sus', 'evil']
SECONDARY_COLUMNS = ['threadId', 'parentProcessId', 'userId', 'mountNamespace', 
                     'processName', 'hostName', 'eventId', 'eventName', 
                     'stackAddresses', 'argsNum', 'returnValue', 'args']

def analyze_csv(file_path):
    try:
        with open(file_path, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            actual_columns = next(reader)
            
            # Check critical columns
            missing_critical = [col for col in CRITICAL_COLUMNS if col not in actual_columns]
            missing_secondary = [col for col in SECONDARY_COLUMNS if col not in actual_columns]
            
            health = "Green"
            if missing_critical:
                health = "Red"
            elif missing_secondary:
                health = "Yellow"
                
            return {
                "path": file_path,
                "health": health,
                "columns": actual_columns,
                "missing_critical": missing_critical,
                "missing_secondary": missing_secondary
            }
    except Exception as e:
        return {
            "path": file_path,
            "health": "Red (Error)",
            "error": str(e)
        }

def main():
    csv_files = glob.glob("**/*.csv", recursive=True)
    results = []
    
    print(f"Scanning {len(csv_files)} files...")
    for file in csv_files:
        res = analyze_csv(file)
        results.append(res)
        
    # Generate dataset_manifest.md
    with open("dataset_manifest.md", "w") as f:
        f.write("# BETH Dataset Manifest\n\n")
        f.write(f"Total files scanned: {len(results)}\n\n")
        
        # Summary table
        f.write("## Health Summary\n\n")
        health_counts = {}
        for r in results:
            h = r['health']
            health_counts[h] = health_counts.get(h, 0) + 1
            
        f.write("| Health | Count |\n| :--- | :--- |\n")
        for h, count in sorted(health_counts.items()):
            f.write(f"| {h} | {count} |\n")
        f.write("\n")
        
        # File listing
        f.write("## File Details\n\n")
        f.write("| File Path | Health | Columns |\n| :--- | :--- | :--- |\n")
        for r in results:
            if 'error' in r:
                f.write(f"| {r['path']} | {r['health']} | Error: {r['error']} |\n")
            else:
                cols_str = ", ".join(r['columns'][:5]) + ("..." if len(r['columns']) > 5 else "")
                f.write(f"| {r['path']} | {r['health']} | {cols_str} |\n")

    print("Manifest generated: dataset_manifest.md")

if __name__ == "__main__":
    main()
