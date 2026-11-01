# VM experiment review

Generated from raw CSVs and run metadata. Failed samples are not equivalent to network packet loss.

| Run | Duration (s) | Interval (s) | Mode | Samples | Success | Timeout | Invalid | Other | Mean RTT (ms) | Mean error (ms) |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20261101-190534 | 60 | 0.5 | baseline | 346 | 280 | 66 | 0 | 0 | 119.156 | 60.233 |
| 20261101-190534 | 60 | 0.5 | optimized | 360 | 360 | 0 | 0 | 0 | 22.892 | 1.158 |
| 20261101-191520 | 60 | 0.5 | baseline | 356 | 283 | 73 | 0 | 0 | 121.607 | 60.927 |
| 20261101-191520 | 60 | 0.5 | optimized | 360 | 360 | 0 | 0 | 0 | 22.259 | 1.110 |
| 20261101-192057 | 60 | 0.5 | baseline | 359 | 285 | 74 | 0 | 0 | 113.563 | 56.615 |
| 20261101-192057 | 60 | 0.5 | optimized | 360 | 360 | 0 | 0 | 0 | 21.959 | 1.049 |
| 20261101-192459 | 60 | 0.5 | baseline | 337 | 240 | 97 | 0 | 0 | 96.142 | 54.041 |
| 20261101-192459 | 60 | 0.5 | optimized | 360 | 360 | 0 | 0 | 0 | 22.097 | 1.034 |
| 20261101-193256 | 60 | 0.5 | baseline | 355 | 272 | 83 | 0 | 0 | 104.701 | 53.329 |
| 20261101-193256 | 60 | 0.5 | optimized | 360 | 360 | 0 | 0 | 0 | 21.992 | 1.048 |

## Failures by phase

| Run | Mode | Phase | Samples | Success | Timeout | Invalid | Other |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 20261101-190534 | baseline | Phase 1: Normal | 120 | 120 | 0 | 0 | 0 |
| 20261101-190534 | baseline | Phase 2: iperf Congestion | 119 | 93 | 26 | 0 | 0 |
| 20261101-190534 | baseline | Phase 3: NetEm Delay+Jitter | 107 | 67 | 40 | 0 | 0 |
| 20261101-190534 | optimized | Phase 1: Normal | 120 | 120 | 0 | 0 | 0 |
| 20261101-190534 | optimized | Phase 2: iperf Congestion | 120 | 120 | 0 | 0 | 0 |
| 20261101-190534 | optimized | Phase 3: NetEm Delay+Jitter | 120 | 120 | 0 | 0 | 0 |
| 20261101-191520 | baseline | Phase 1: Normal | 120 | 120 | 0 | 0 | 0 |
| 20261101-191520 | baseline | Phase 2: iperf Congestion | 112 | 78 | 34 | 0 | 0 |
| 20261101-191520 | baseline | Phase 3: NetEm Delay+Jitter | 124 | 85 | 39 | 0 | 0 |
| 20261101-191520 | optimized | Phase 1: Normal | 120 | 120 | 0 | 0 | 0 |
| 20261101-191520 | optimized | Phase 2: iperf Congestion | 120 | 120 | 0 | 0 | 0 |
| 20261101-191520 | optimized | Phase 3: NetEm Delay+Jitter | 120 | 120 | 0 | 0 | 0 |
| 20261101-192057 | baseline | Phase 1: Normal | 120 | 120 | 0 | 0 | 0 |
| 20261101-192057 | baseline | Phase 2: iperf Congestion | 116 | 74 | 42 | 0 | 0 |
| 20261101-192057 | baseline | Phase 3: NetEm Delay+Jitter | 123 | 91 | 32 | 0 | 0 |
| 20261101-192057 | optimized | Phase 1: Normal | 120 | 120 | 0 | 0 | 0 |
| 20261101-192057 | optimized | Phase 2: iperf Congestion | 120 | 120 | 0 | 0 | 0 |
| 20261101-192057 | optimized | Phase 3: NetEm Delay+Jitter | 120 | 120 | 0 | 0 | 0 |
| 20261101-192459 | baseline | Phase 1: Normal | 120 | 120 | 0 | 0 | 0 |
| 20261101-192459 | baseline | Phase 2: iperf Congestion | 96 | 46 | 50 | 0 | 0 |
| 20261101-192459 | baseline | Phase 3: NetEm Delay+Jitter | 121 | 74 | 47 | 0 | 0 |
| 20261101-192459 | optimized | Phase 1: Normal | 120 | 120 | 0 | 0 | 0 |
| 20261101-192459 | optimized | Phase 2: iperf Congestion | 120 | 120 | 0 | 0 | 0 |
| 20261101-192459 | optimized | Phase 3: NetEm Delay+Jitter | 120 | 120 | 0 | 0 | 0 |
| 20261101-193256 | baseline | Phase 1: Normal | 120 | 120 | 0 | 0 | 0 |
| 20261101-193256 | baseline | Phase 2: iperf Congestion | 118 | 77 | 41 | 0 | 0 |
| 20261101-193256 | baseline | Phase 3: NetEm Delay+Jitter | 117 | 75 | 42 | 0 | 0 |
| 20261101-193256 | optimized | Phase 1: Normal | 120 | 120 | 0 | 0 | 0 |
| 20261101-193256 | optimized | Phase 2: iperf Congestion | 120 | 120 | 0 | 0 | 0 |
| 20261101-193256 | optimized | Phase 3: NetEm Delay+Jitter | 120 | 120 | 0 | 0 | 0 |

TIMEOUT means no valid reply arrived within the socket wait. INVALID means a reply was received
but failed packet/request validation. Neither count alone establishes network packet loss.
A late reply can also affect the next attempt; inspect client logs alongside the phase counts.
RTT uses successful samples only. Error is measured after correction and includes failed attempts.

## Automatic recovery

- 20261101-194117: PASS; Path B requests=108; Path A counter=132 → 204.

## Incomplete runs excluded

20261101-185338, 20261101-185404, 20261101-185417, 20261101-185649
