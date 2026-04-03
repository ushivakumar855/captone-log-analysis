import csv
import glob
import os

THREAT_PATTERNS = {
    "reverse_shell": ["bash", "sh", "nc", "python", "perl", "ruby", "php"],
    "trojan_mimics": ["kworker", "systemd", "kthread", "migration", "cpuhp"],
    "ssh_hijack": ["sshd"]
}

def hunt():
    results = []
    csv_files = glob.glob("**/*.csv", recursive=True)
    
    for file_path in csv_files:
        try:
            with open(file_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('evil') == '1':
                        process = row.get('processName', '').lower()
                        args = row.get('args', '').lower()
                        
                        threat_type = "Unknown Malicious"
                        
                        if any(p in process for p in THREAT_PATTERNS["reverse_shell"]) and ("/dev/tcp" in args or " -e " in args or "connect" in row.get('eventName', '')):
                            threat_type = "Potential Reverse Shell"
                        elif any(p == process for p in THREAT_PATTERNS["trojan_mimics"]) and row.get('userId') != '0':
                            threat_type = "System Trojan (Mimicry)"
                        elif "sshd" in process and ("shadow" in args or ".ssh" in args):
                            threat_type = "SSH Hijacking/Credential Theft"
                            
                        results.append({
                            "file": file_path,
                            "process": process,
                            "args": args,
                            "type": threat_type,
                            "timestamp": row.get('timestamp')
                        })
        except:
            continue
    return results

def main():
    findings = hunt()
    
    with open("threat_analysis.md", "w") as f:
        f.write("# BETH Threat Analysis Report\n\n")
        f.write(f"Total Malicious Events Identified: {len(findings)}\n\n")
        f.write("| Timestamp | Process | Threat Type | File Source |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        for res in findings[:100]:
            f.write(f"| {res['timestamp']} | {res['process']} | {res['type']} | {res['file']} |\n")

    print(f"Found {len(findings)} malicious events. Summary written to threat_analysis.md")

if __name__ == "__main__":
    main()
