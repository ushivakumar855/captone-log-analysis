# 3_threat_analysis_report.md

## Total Threats Found: 53119

### Analysis of Attack Types
Based on the search patterns and behavioral analysis, here are the identified threats found in the dataset:

| Timestamp | File | Process | Type | Detailed Behavior |
| :--- | :--- | :--- | :--- | :--- |
| 411.014724 | 13_labelled_testing_data/part3.csv | sshd | **Reverse Shell** | Potential reverse shell behavior in 'sshd': [{'name': 'sockfd', 'type': 'int', 'value': 6}, {'name': 'addr', 'type': 'struct sockaddr*', 'value' |
| 461.461695 | 13_labelled_testing_data/part10.csv | tsm | **System Management Trojan** | Process 'tsm' mimicking system service under user 1001. |
| None | 10_labelled_2021may-ip-10-100-1-95-dns/part_1_10.csv |  | **Unclassified Malicious/Suspicious** | Generic anomalous activity flagged by dataset labels. |


### Frequency Summary (Sample Distribution)

- **Reverse Shell**: 750 occurrences in analyzed sample.
- **System Management Trojan**: 16482 occurrences in analyzed sample.
- **Unclassified Malicious/Suspicious**: 35887 occurrences in analyzed sample.
