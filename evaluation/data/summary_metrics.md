# Network Time Synchronization — Benchmark Performance Summary

| Metric | Baseline Mode (No SDN) | SDN-Optimized Mode | Improvement (%) |
| :--- | :---: | :---: | :---: |
| Mean RTT (ms) | 53.210 | 6.611 | **+87.58%** |
| P95 RTT (ms) | 106.975 | 7.957 | **+92.56%** |
| Mean Jitter (ms) | 9.190 | 1.016 | **+88.95%** |
| Mean Clock Error (ms) | 22.440 | 0.321 | **+98.57%** |
| P95 Clock Error (ms) | 47.691 | 0.576 | **+98.79%** |
| Max Clock Error (ms) | 52.139 | 12.291 | **+76.43%** |
| Convergence Time (s) | 1.00 | 1.01 | -1.00% |

> Legacy output: the runtime and run parameters for these measurements were not recorded. Do not treat this table as verified Mininet results. Generate a new comparison with the Linux VM runner.
