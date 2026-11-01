# Network Time Synchronization — Benchmark Performance Summary

| Metric | Baseline Mode (No SDN) | SDN-Optimized Mode | Improvement (%) |
| :--- | :---: | :---: | :---: |
| Mean RTT (ms) | 54.199 | 6.315 | **+88.35%** |
| P95 RTT (ms) | 110.588 | 7.630 | **+93.10%** |
| Mean Jitter (ms) | 9.207 | 0.964 | **+89.53%** |
| Mean Clock Error (ms) | 23.152 | 0.314 | **+98.64%** |
| P95 Clock Error (ms) | 50.327 | 0.611 | **+98.79%** |
| Max Clock Error (ms) | 59.397 | 11.018 | **+81.45%** |
| Convergence Time (s) | 1.00 | 1.00 | **+0.00%** |

> **Key Takeaway:** SDN-driven OpenFlow classification and dynamic Path B failover reduce tail RTT bufferbloat and maintain sub-millisecond clock synchronization even under severe 12 Mbps link congestion and link jitter.