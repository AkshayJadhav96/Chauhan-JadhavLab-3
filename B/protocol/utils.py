import time

def calc_latency_ms(t0_ns, t1_ns):
    if t0_ns > 0:
        return (t1_ns - t0_ns) / 1_000_000
    return None

def print_latency(t0_ns, t1_ns):
    latency = calc_latency_ms(t0_ns, t1_ns)
    if latency is not None:
        print(f"One-way latency: {latency:.2f} ms")
