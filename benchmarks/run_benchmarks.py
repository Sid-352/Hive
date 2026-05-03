import asyncio
import time
import os
import json
import statistics
import uuid
import struct
import gc
from app.core.data_plane import DataPlane
from app.core.security import SecurityManager
from app.core.controller import AppController

class MockAgent:
    def __init__(self, score):
        self.vitality_score = score
        self.response_queue = asyncio.Queue()
    async def start(self):
        await self.response_queue.put({"type": "STATUS", "state": "READY", "version": "1.1.1"})
    async def stop(self): pass
    async def send_command(self, cmd):
        if cmd['type'] == 'GET_TELEMETRY':
            await self.response_queue.put({"type": "TELEMETRY", "vitality_score": self.vitality_score})
        elif cmd['type'] == 'CREATE_GROUP':
            await self.response_queue.put({"type": "GROUP_CREATED", "is_group_owner": True})

class BenchmarkDataPlane(DataPlane):
    def __init__(self, security, chunk_size=128*1024):
        super().__init__(security)
        self.chunk_size = chunk_size

    async def send_file(self, path: str, resume_offset: int = 0, progress_cb=None) -> None:
        if not self._connected: raise RuntimeError("DataPlane not connected")
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(resume_offset)
            sent = resume_offset
            while sent < size:
                chunk = f.read(self.chunk_size)
                if not chunk: break
                aad = struct.pack(">Q", sent)
                await self._write_framed(self.security.encrypt(chunk, aad=aad))
                sent += len(chunk)
                if progress_cb: progress_cb(sent, size)

async def benchmark_throughput():
    print("\n[1/3] Benchmarking Throughput vs. Chunk Size...")
    results = []
    chunk_sizes = [16, 32, 64, 128, 256, 512, 1024] # KB
    file_size_mb = 50 
    test_data = os.urandom(file_size_mb * 1024 * 1024)
    
    print("  (Deriving Argon2id key for realism...)")
    sec = SecurityManager("123456") 
    
    for size_kb in chunk_sizes:
        size_bytes = size_kb * 1024
        src_file = f"temp_src_{size_kb}.bin"
        dst_file = f"temp_dst_{size_kb}.bin"
        with open(src_file, "wb") as f: f.write(test_data)
        
        async def real_transfer():
            rx = DataPlane(sec)
            tx = BenchmarkDataPlane(sec, chunk_size=size_bytes)
            
            connected_event = asyncio.Event()
            rx_done = asyncio.Event()

            async def handle_rx(reader, writer):
                rx._reader = reader
                rx._writer = writer
                rx._connected = True
                connected_event.set()
                try:
                    await rx.receive_file(dst_file, len(test_data))
                finally:
                    await rx.disconnect()
                    rx_done.set()

            srv = await asyncio.start_server(handle_rx, '127.0.0.1', 0)
            addr = srv.sockets[0].getsockname()
            
            await tx.connect(str(addr[1]))
            await connected_event.wait()
            
            start = time.perf_counter()
            await tx.send_file(src_file)
            await tx.disconnect()
            await rx_done.wait()
            duration = time.perf_counter() - start
            
            srv.close()
            await srv.wait_closed()
            return duration

        try:
            durations = []
            for _ in range(3): # 3 runs
                durations.append(await real_transfer())
                await asyncio.sleep(0.1)
            
            avg_dur = statistics.mean(durations)
            speed = file_size_mb / avg_dur
            print(f"  - Chunk Size {size_kb:4} KB: {speed:6.2f} MB/s (Avg {avg_dur:.4f}s)")
            results.append({"chunk_kb": size_kb, "speed_mbs": speed})
        finally:
            gc.collect()
            for _ in range(5):
                try:
                    if os.path.exists(src_file): os.remove(src_file)
                    if os.path.exists(dst_file): os.remove(dst_file)
                    break
                except PermissionError:
                    await asyncio.sleep(0.2)

    return results

async def benchmark_election():
    print("\n[2/3] Benchmarking Election Convergence...")
    results = []
    peer_counts = [2, 5, 10, 20]
    
    for count in peer_counts:
        ctrl = AppController(room_pin="1234", agent_override=None, debug=True)
        ctrl.agent = MockAgent(50)
        await ctrl.agent.start()
        
        from app.core.network import NetworkManager
        ctrl.network = NetworkManager(
            node_uuid=str(uuid.uuid4()),
            node_name="BenchmarkNode",
            score=50,
            pin="1234",
            security=ctrl.security,
            bus=ctrl.bus
        )
        
        start_time = time.perf_counter()
        
        for i in range(count):
            p_uuid = str(uuid.uuid4())
            ctrl.network.peers[p_uuid] = {
                "name": f"Peer_{i}",
                "score": 10 + i,
                "last_seen": time.time(),
                "ip": "127.0.0.1"
            }
        
        ctrl.network._elect_host()
        
        duration = (time.perf_counter() - start_time) * 1000 # ms
        print(f"  - Nodes {count:2}: {duration:6.4f} ms to elect leader")
        results.append({"nodes": count, "time_ms": duration})
        
        ctrl.shutdown()
        
    return results

async def benchmark_recovery():
    print("\n[3/3] Benchmarking Recovery/Resume Latency...")
    # Increase to 100MB to see real timing
    file_size_mb = 100
    test_data = os.urandom(file_size_mb * 1024 * 1024)
    sec = SecurityManager("123456")
    
    src_file = "recovery_src.bin"
    dst_file = "recovery_dst.bin"
    with open(src_file, "wb") as f: f.write(test_data)
    
    async def get_transfer_time(resume_at=0):
        if resume_at > 0:
            with open(dst_file, "wb") as f: f.write(test_data[:resume_at])
        else:
            if os.path.exists(dst_file):
                try: os.remove(dst_file)
                except PermissionError: pass
            
        rx = DataPlane(sec)
        tx = DataPlane(sec)
        connected_event = asyncio.Event()
        rx_done = asyncio.Event()
        async def handle_rx(reader, writer):
            rx._reader = reader
            rx._writer = writer
            rx._connected = True
            connected_event.set()
            try:
                await rx.receive_file(dst_file, len(test_data), resume_offset=resume_at)
            finally:
                await rx.disconnect()
                rx_done.set()

        srv = await asyncio.start_server(handle_rx, '127.0.0.1', 0)
        addr = srv.sockets[0].getsockname()
        await tx.connect(str(addr[1]))
        await connected_event.wait()
        
        start = time.perf_counter()
        await tx.send_file(src_file, resume_offset=resume_at)
        await tx.disconnect()
        await rx_done.wait()
        duration = time.perf_counter() - start
        srv.close()
        await srv.wait_closed()
        return duration

    print("  (Running baseline 100MB transfer...)")
    baseline = await get_transfer_time(0)
    print(f"  - Baseline (100MB Full): {baseline:.4f}s")
    await asyncio.sleep(0.5)
    
    print("  (Running 50MB resume...)")
    resume_50 = await get_transfer_time(file_size_mb * 1024 * 1024 // 2)
    print(f"  - Resume (at 50%):      {resume_50:.4f}s")
    
    improvement = (baseline - resume_50) / baseline * 100
    print(f"  - Efficiency Gain:      {improvement:.2f}%")
    
    for _ in range(5):
        try:
            if os.path.exists(src_file): os.remove(src_file)
            if os.path.exists(dst_file): os.remove(dst_file)
            break
        except PermissionError:
            await asyncio.sleep(0.2)
    
    return {"baseline": baseline, "resume_50": resume_50, "gain": improvement}

async def main():
    print("=== Hive Academic Benchmarking Suite (V2: High Fidelity) ===")
    t_results = await benchmark_throughput()
    e_results = await benchmark_election()
    r_results = await benchmark_recovery()
    
    print("\n" + "="*40)
    print("FINAL SUMMARY FOR IEEE/ARXIV DRAFTS")
    print("="*40)
    
    print("\nTable 1: Throughput Performance")
    print("| Chunk Size (KB) | Throughput (MB/s) |")
    print("|-----------------|-------------------|")
    for r in t_results:
        print(f"| {r['chunk_kb']:15} | {r['speed_mbs']:17.2f} |")
        
    print("\nTable 2: Election Scalability")
    print("| Node Count | Convergence Time (ms) |")
    print("|------------|-----------------------|")
    for r in e_results:
        print(f"| {r['nodes']:10} | {r['time_ms']:21.4f} |")

    print(f"\nResilience Analysis:")
    print(f"- Recovery Overhead (Resume at 50%): {r_results['resume_50']:.4f}s")
    print(f"- Time Saved vs. Retransmission:    {r_results['gain']:.2f}%")
    
if __name__ == "__main__":
    asyncio.run(main())
