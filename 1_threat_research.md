# 1_threat_research.md

## Objective
Research the specific indicators of compromise (IoCs) for the BETH dataset, specifically targeting:
1.  Reverse Shells
2.  System Management Trojans
3.  SSH Hijacking Attacks

## Google Search Findings
Based on our research, the BETH dataset captures real-world attacks on honeypots. Key findings include:

### 1. Attack Patterns in BETH
- **Botnet/Scanner Activity**: Large volumes of `connect` calls (often port 22/SSH or 80/HTTP) from a single process to various IPs.
- **Cryptomining**: Unusual process names or system-mimicking processes (`tsm`, `kworker` but with high CPU or unusual `userId`).
- **Initial Access**: Usually via SSH, followed by rapid setup operations.
- **Out-of-Distribution**: `evil=1` events are exclusively in the `testing` subset and represent active attacks.

### 2. Behavioral Indicators (BPF Logs)
- **Reverse Shell**:
    - Process: `bash`, `sh`, `nc`, `python`, `perl`.
    - Event: `execve` with arguments containing `/dev/tcp`, `-e`, or pipes.
    - Event: `connect` following a shell execution.
- **System Management Trojans**:
    - Process: Mimicking legitimate names like `systemd`, `kworker`, `tsm`, `ls`.
    - Context: `userId` is often non-root (>= 1000) but performing system-level actions.
    - Behavior: Writing to `/etc/` or `/var/spool/cron/`.
- **SSH Hijacking**:
    - Process: `sshd` as a parent spawning malicious children.
    - Event: Reading `/etc/shadow` or `.ssh/authorized_keys`.
    - Pattern: Brute-forcing (many `connect` attempts to port 22).

## Interpretation of 'args' Column
The `args` column contains a serialized list of system call arguments.
- **`name`**: Argument name (e.g., `pathname`, `argv`, `addr`).
- **`type`**: Data type (e.g., `const char*`, `int`).
- **`value`**: The actual content. For `execve`, this is the command line. For `connect`, this includes the IP and Port.

## Strategy for Hunting
1.  Filter for `evil=1`.
2.  Analyze `processName` and `args` for the patterns identified above.
3.  Cross-reference `processId` and `parentProcessId` to see the "spawn tree".
