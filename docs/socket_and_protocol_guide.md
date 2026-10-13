# Socket Application & Protocol Guide

---

## 1. How to Run the Code

### 1.1 Start the Server (Host 1 / Reference Clock)
```bash
python3 -m app.server --port 12300 --workers 4
```

### 1.2 Start the Client (Host 2 / Drifting Node)
```bash
# Step mode (instant jump):
python3 -m app.client --server-ip 127.0.0.1 --port 12300 --client-id 1 --drift-rate 0.020 --initial-offset 2.0 --interval 1.0 --method step

# Slew mode (gradual adjustment):
python3 -m app.client --server-ip 127.0.0.1 --port 12300 --client-id 1 --drift-rate 0.020 --initial-offset 0.1 --interval 1.0 --method slew
```
- Logs are automatically saved to `data/client_{client_id}_sync.csv`.

### 1.3 Run Background Traffic (for SDN Congestion Testing)
```bash
# 1. Start the sink receiver on port 5001:
python3 -m app.background_traffic --server --port 5001

# 2. Blast 20 Mbps background traffic to the sink:
python3 -m app.background_traffic --target 127.0.0.1 --port 5001 --rate 20.0 --duration 10.0
```

### 1.4 Run All Unit Tests
```bash
python3 -m unittest discover -s tests -v
```

---

## 2. Packet Format & Math (`app/protocol.py`)

### 2.1 The 4 Timestamps:
- **t0**: Client transmits request (client virtual clock)
- **t1**: Server receives request (server master clock)
- **t2**: Server transmits response (server master clock)
- **t3**: Client receives response (client virtual clock)

### 2.2 Mathematical Formulas:
- **Round-Trip Delay (RTT)**: `Delay = (t3 - t0) - (t2 - t1)`
- **Clock Offset**: `Offset = ((t1 - t0) + (t2 - t3)) / 2`
- **Corrected Time**: `Corrected_Time = Virtual_Clock + Offset`

### 2.3 35-Byte Binary Packet Structure (`!4sBHIddd`):
- `4s` (4 bytes): Magic bytes `b"NTPS"`
- `B` (1 byte): Packet type (`1` = Request, `2` = Response)
- `H` (2 bytes): Client ID (`0 - 65535`)
- `I` (4 bytes): Sequence number (`0 - 4B`)
- `ddd` (24 bytes): `t0`, `t1`, `t2` (three 8-byte 64-bit floats)

---

## 3. CSV Schema for Member 3 (`data/client_{id}_sync.csv`)

Member 3's `evaluation/plot_results.py` can read these columns:
`timestamp, client_id, seq_num, t0, t1, t2, t3, rtt, offset, status`

- `rtt`: Delay in milliseconds.
- `offset`: Clock offset in milliseconds.
- `status`: `SUCCESS` or `TIMEOUT`.
