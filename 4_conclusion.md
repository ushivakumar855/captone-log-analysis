# 4_conclusion.md

## Final Summary of Findings

Our investigation into the BETH dataset has successfully identified and located several types of malicious activity using behavioral analysis of BPF logs.

### 1. Reverse Shell Patterns
- **Where**: Primarily found in the `13_labelled_testing_data/` subset (e.g., `part3.csv` at timestamp `411.014724`).
- **What is happening**: We identified `sshd` and shell processes (`bash`, `sh`) initiating outbound `connect` calls. In a standard environment, `sshd` should only be listening. An outbound `connect` from a process spawned by a shell is a classic indicator of a reverse shell being established to a Command and Control (C2) server.
- **Args Column**: In these cases, the `args` column contains the `struct sockaddr*` with the destination IP and port.

### 2. System Management Trojans
- **Where**: Widespread across the testing data (e.g., `13_labelled_testing_data/part10.csv` and many others).
- **What is happening**: The process `tsm` is a primary culprit. It mimics a system name but runs under `userId: 1001` (external/non-root). It performs thousands of `connect` calls in a very short period (milliseconds), which is characteristic of a **Botnet Scanner** or a **Cryptomining** agent checking in with its pool.
- **Behavior**: It uses the `connect` syscall to scan the internal network (192.168.0.x) on port 22 (SSH), likely attempting to move laterally.

### 3. SSH Hijacking & Lateral Movement
- **Where**: Identified in the `connect` events originating from `tsm` and `sshd` processes.
- **What is happening**: The "SSH Scanning" behavior (attempting to connect to port 22 on multiple IPs) is the first stage of SSH hijacking. The goal is to find other vulnerable hosts to spread the infection.
- **Args Column**: The `args` column reveals the targets. For example, `sin_addr: 192.168.0.35, sin_port: 22`.

## Technical Definitions for the 'args' Column
The `args` column is the most critical for understanding *intent*.
- **For `connect`**: It tells you *who* the machine is talking to (IP/Port).
- **For `execve`**: It tells you the *exact command* being run (e.g., `curl http://... | sh`).
- **For `openat`**: It tells you *which file* is being accessed (e.g., `/etc/shadow`).

By combining the `evil=1` label with these behavioral signatures, we can precisely identify the stages of the attack from initial entry to lateral movement and payload execution.
