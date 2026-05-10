import subprocess
import re
import matplotlib.pyplot as plt
import os

# ==========================================
# Configuration
# ==========================================
# Sweep based on Global Target Gbps
TARGET_RATES_GBPS = [10, 12, 14, 16, 18, 20] #, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40]
TARGET_RATES_GBPS = [x * 1000 for x in TARGET_RATES_GBPS]

NUM_CLUSTERS = 100 
TILE_SIZE_BYTES = 16384
TOTAL_TRANSFERS = 10000
TOTAL_BITS = TOTAL_TRANSFERS * TILE_SIZE_BYTES * 8

SOURCE_FILE = "pulp/pulp/chips/softhier/sw/app_example/main.c"
APP_ARG = "" 

target_rates_plot_gbps = []
achieved_throughputs_bps = []
latencies_cycles = []

def update_c_macro(filepath, macro_name, new_value):
    """Directly modifies the #define in the C file to bypass CMake quirks."""
    with open(filepath, 'r') as file:
        content = file.read()
    
    pattern = rf"(#define\s+{macro_name}\s+)\d+"
    replacement = rf"\g<1>{new_value}"
    
    new_content = re.sub(pattern, replacement, content)
    
    with open(filepath, 'w') as file:
        file.write(new_content)

# ==========================================
# Automation Loop
# ==========================================
for target_gbps in TARGET_RATES_GBPS:
    
    # Calculate Cycles Per Packet based on target Gbps
    # 1 GHz Clock -> 1 Gbps = 1 bit/cycle
    rate_per_cluster_gbps = target_gbps / NUM_CLUSTERS
    packet_bits = TILE_SIZE_BYTES * 8
    
    # If target rate exceeds max theoretical, set delay to 0 to unleash max throughput
    if rate_per_cluster_gbps > 0 and (packet_bits / rate_per_cluster_gbps) > 1:
        cycles_per_packet = int(packet_bits / rate_per_cluster_gbps)
    else:
        cycles_per_packet = 0
        
    print(f"[*] Simulating Target: {target_gbps} Gbps (Pacing: 1 packet every {cycles_per_packet} cycles/cluster)...")
    
    # Update the new macro
    update_c_macro(SOURCE_FILE, "CYCLES_PER_PACKET", cycles_per_packet)
    
    compile_cmd = f"make sh-sw {APP_ARG}"
    try:
        subprocess.run(compile_cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) #replace devnulls with capture_output=True, text=True to see errors
    except subprocess.CalledProcessError as e:
        print(f"    -> ERROR: Compilation failed for target {target_gbps} Gbps")
        print("    -> COMPILER ERROR LOG:")
        print(e.stderr)
        continue
    
    run_cmd = "make sh-run"
    result = subprocess.run(run_cmd, shell=True, capture_output=True, text=True)
    output = result.stdout
    
    match = re.search(r"Execution period is (\d+) ns", output)
    match_lat = re.search(r"Global Average Packet Latency:\s+([\d.]+)\s+cycles", output) 
    
    # --- Parse the WIDE Routers table for congestion metrics ---
    total_routed = 0
    total_stalled = 0
    
    # Regex matches rows like: "  13   |     371520 |      74262 |      16.66 %"
    for rm in re.finditer(r"^\s*\d+\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*[\d.]+\s*\%", output, re.MULTILINE):
        total_routed += int(rm.group(1))
        total_stalled += int(rm.group(2))
        
    global_congestion_rate = 0.0
    if (total_routed + total_stalled) > 0:
        global_congestion_rate = (total_stalled / (total_routed + total_stalled)) * 100.0
    # ----------------------------------------------------------------
    
    if match and match_lat:
        exec_time_ns = float(match.group(1))
        exec_time_s = exec_time_ns * 1e-9
        
        # Calculate actual Throughput
        throughput_bps = TOTAL_BITS / exec_time_s
        avg_packet_lat_cycles = float(match_lat.group(1))
        
        target_rates_plot_gbps.append(target_gbps)
        achieved_throughputs_bps.append(throughput_bps)
        latencies_cycles.append(avg_packet_lat_cycles)
        
        print(f"    -> Avg Pkt Latency: {avg_packet_lat_cycles:.2f} cycles | Actual Throughput: {throughput_bps / 1e9:.2f} Gbps | Congestion: {global_congestion_rate:.2f}%")
    else:
        print("    -> ERROR: Could not parse execution time or latency!")

# ==========================================
# Plotting the Results
# ==========================================

# ---------------------------------------------------------
# Plot 1: Average Packet Latency vs. Target Rate
# ---------------------------------------------------------
plt.figure(figsize=(10, 6))

plt.plot(target_rates_plot_gbps, latencies_cycles, marker='o', linestyle='-', color='r', linewidth=2, label="Flex-2DMesh")

plt.title("Average Packet Latency vs Injection Rate", fontsize=14, fontweight='bold')
plt.xlabel("Injection Rate (Gbps)", fontsize=12)
plt.ylabel("Average Packet Latency (Clock Cycles)", fontsize=12) 
plt.grid(True, which="both", ls="--", alpha=0.7)
plt.legend()

plt.savefig("2dmesh_latency.png", dpi=300)
print("\n[*] Plot 1 saved as 2dmesh_latency.png")
plt.show()

# ---------------------------------------------------------
# Plot 2: Achieved Throughput vs. Target Rate
# ---------------------------------------------------------
plt.figure(figsize=(10, 6))

achieved_gbps = [rate / 1e9 for rate in achieved_throughputs_bps]

# Plot the achieved throughput
plt.plot(target_rates_plot_gbps, achieved_gbps, marker='s', linestyle='-', color='b', linewidth=2, label="Achieved Throughput")

# Plot an "Ideal" reference line where Achieved == Target
# plt.plot(target_rates_plot_gbps, target_rates_plot_gbps, linestyle='--', color='gray', linewidth=1.5, label="Ideal (Achieved = Target)")

plt.title("Achieved Throughput vs Injection Rate", fontsize=14, fontweight='bold')
plt.xlabel("Injection Rate (Gbps)", fontsize=12)
plt.ylabel("Achieved Throughput (Gbps)", fontsize=12) 
plt.grid(True, which="both", ls="--", alpha=0.7)
plt.legend()

plt.savefig("2dmesh_throughput.png", dpi=300)
print("[*] Plot 2 saved as 2dmesh_throughput.png")
plt.show()