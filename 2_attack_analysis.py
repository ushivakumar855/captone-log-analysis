import csv
import glob
import os

# Define the IoC patterns
PATTERNS = {
    "Reverse Shell": ["bash", "sh", "nc", "python", "perl", "ruby", "php"],
    "System Trojan": ["tsm", "kworker", "systemd", "kthread", "migration"],
    "SSH Hijacking": ["sshd"]
}

def hunt_threats():
    findings = []
    # Search all CSV files to find different stages of the attack
    csv_files = glob.glob("**/*.csv", recursive=True)
    
    for file_path in csv_files:
        try:
            with open(file_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                # Sample up to 500 rows per file to find diverse patterns across many files
                row_count = 0
                for row in reader:
                    row_count += 1
                    if row_count > 500: break
                    
                    # Look for BOTH 'evil=1' and 'sus=1' since 'evil' is only in testing set
                    if row.get('evil') == '1' or row.get('sus') == '1':
                        process = row.get('processName', '').lower()
                        args = row.get('args', '').lower()
                        event = row.get('eventName', '').lower()
                        
                        threat_type = "Unclassified Malicious/Suspicious"
                        description = "Generic anomalous activity flagged by dataset labels."
                        
                        # Identify specific attacks
                        if any(p in process for p in PATTERNS["Reverse Shell"]):
                            if "/dev/tcp" in args or " -e " in args or "connect" in event:
                                threat_type = "Reverse Shell"
                                description = f"Potential reverse shell behavior in '{process}': {args[:100]}"
                        
                        elif any(p == process for p in PATTERNS["System Trojan"]):
                            if row.get('userId') != '0' and row.get('userId') != '':
                                threat_type = "System Management Trojan"
                                description = f"Process '{process}' mimicking system service under user {row.get('userId')}."
                        
                        elif "sshd" in process:
                            if "shadow" in args or ".ssh" in args or "authorized_keys" in args:
                                threat_type = "SSH Hijacking (Credential Theft)"
                                description = f"SSH daemon '{process}' accessed sensitive credential files."
                            elif "connect" in event and ("'sin_port': '22'" in args or "22" in args):
                                threat_type = "SSH Scanning/Brute-forcing"
                                description = f"SSH connection attempt to remote host detected."

                        findings.append({
                            "File": file_path,
                            "Timestamp": row.get('timestamp'),
                            "Process": process,
                            "Event": event,
                            "Type": threat_type,
                            "Description": description,
                            "Args_Preview": args[:200]
                        })
        except Exception as e:
            continue
    return findings

def main():
    print("Hunting for specific BETH threats...")
    results = hunt_threats()
    
    # Write report
    with open("3_threat_analysis_report.md", "w") as f:
        f.write("# 3_threat_analysis_report.md\n\n")
        f.write(f"## Total Threats Found: {len(results)}\n\n")
        f.write("### Analysis of Attack Types\n")
        f.write("Based on the search patterns and behavioral analysis, here are the identified threats found in the dataset:\n\n")
        
        f.write("| Timestamp | File | Process | Type | Detailed Behavior |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        
        # Collect one clear example for each type found
        examples = {}
        type_counts = {}
        for res in results:
            t = res['Type']
            type_counts[t] = type_counts.get(t, 0) + 1
            if t not in examples:
                examples[t] = res

        # Sort examples by type for consistent reporting
        for t in sorted(examples.keys()):
            res = examples[t]
            f.write(f"| {res['Timestamp']} | {res['File']} | {res['Process']} | **{res['Type']}** | {res['Description']} |\n")

        f.write("\n\n### Frequency Summary (Sample Distribution)\n\n")
        for t in sorted(type_counts.keys()):
            f.write(f"- **{t}**: {type_counts[t]} occurrences in analyzed sample.\n")

if __name__ == "__main__":
    main()
