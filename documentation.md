# BETH Dataset: Comprehensive Deep Dive Report

## 1. Executive Summary & Master Index
The BETH (BPF-extended tracking honeypot) dataset is a 2021 collection of eBPF-captured kernel events designed for anomaly detection. This exploration has analyzed over 3.8 million events across training, testing, and validation splits, correlating process-level behavior with DNS network activity.

| Category | Description | Key Insight |
| :--- | :--- | :--- |
| **Training Data** | Benign baseline activity. | dominated by system maintenance (`ps`, `sshd`, `systemd`). |
| **Testing/Validation** | Evaluation sets with attack injections. | High concentration of `evil` labels in `tsm` process events. |
| **DNS Logs** | Host networking metadata. | Correlates with external IP connections seen in kernel `connect` calls. |

---

## 2. Behavioral Patterns & Malicious Profiles

### The "Evil" Signature
Analysis of `evil == 1` events reveals a highly specific behavioral signature:
- **Primary Process:** `tsm` (Total Security Management or similar, likely the attacker's tool in this honeypot context) accounts for the vast majority of malicious logs.
- **Top Malicious Event:** `connect`. The attack pattern involves heavy networking, with processes attempting to connect to external/internal IPs (e.g., ports 22 for SSH pivoting).
- **Secondary Malicious Processes:** `sshd` (brute force/pivoting), `passwd` (credential tampering), `w` (user surveillance), and `systemctl` (persistence).

### User ID Distribution
- **User 0 (Root):** 93%+ of all logs. Most malicious activity occurs under the root context or attempts to escalate to it.
- **User 1001:** Significant secondary user, likely a service or target account for non-root anomalies.

---

## 3. Top Features Analysis

### Most Frequent Processes (Across All Data)
1. `ps` (Process status checks - very high frequency)
2. `sshd` (SSH daemon activity)
3. `systemd-udevd` (Device management)
4. `tsm` (The primary malicious agent)

### Most Frequent Kernel Events
1. `close` / `openat` (File system interactions)
2. `security_file_open` (Kernel-level security checks)
3. `connect` (Network socket initialization - **Critical for Evil detection**)

---

## 4. DNS Correlation
The DNS logs (`*_dns/` folders) provide the network-layer context for the kernel-level `connect` calls.
- **Benign DNS:** Heavy traffic to `ssm.us-east-2.amazonaws.com` (Standard AWS management).
- **Attack DNS:** Queries matching the IPs found in the `evil` `args` column (e.g., `192.168.0.x` range in samples).

---

## 5. Health Check & Data Integrity
- **Missing Values:** High null counts in `DnsAnswer` columns in DNS logs (typical for NXDOMAIN or initial queries).
- **Args Complexity:** The `args` column contains JSON-like nested structures. For ML, these must be flattened or embedded (e.g., extracting `sin_addr` from `connect` calls).
- **Label Imbalance:** Malicious events are rare (~5% or less), requiring specialized sampling or loss functions.

---

## 6. Directory Structure Map (Detailed)
- `1_labelled_...` to `12_labelled_...`: Host-specific snapshots (e.g., `ip-10-100-1-105`).
- `13_labelled_testing_data`: Aggregated evaluation set.
- `14_labelled_training_data`: Aggregated training set.
- `15_labelled_validation_data`: Aggregated tuning set.
