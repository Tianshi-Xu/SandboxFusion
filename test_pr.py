import psutil
import os
import time
import sys

print("--- [Verification Start] ---")
print(f"Python executable: {sys.executable}")

# --- 1. 验证 PID 命名空间 ---
print("\n--- [Test 1: PID Namespace Verification] ---")

my_pid = os.getpid()
pid1_cmd = ""  # <-- 修复：在这里初始化变量
print(f"This script's PID is: {my_pid}")

try:
    all_pids_count = len(list(psutil.pids()))
    print(f"Total processes visible to this container: {all_pids_count}")
except Exception as e:
    all_pids_count = -1
    print(f"Could not list all pids: {e}")

try:
    pid1_process = psutil.Process(1)
    pid1_cmd = " ".join(pid1_process.cmdline())
    print(f"PID 1 command: '{pid1_cmd}'")
except Exception as e:
    print(f"Could not get info for PID 1: {e}")

if all_pids_count > 50 or "systemd" in pid1_cmd or "init" in pid1_cmd:
    print(">>> [Test 1 Result]: PID Namespace is SHARED with Host (Standard).")
elif all_pids_count == -1:
    print(">>> [Test 1 Result]: Unknown. Security prevents listing all PIDs.")
else:
    print(">>> [Test 1 Result]: Custom Sandbox Environment DETECTED.")
    print(f"    (High PID {my_pid} but Low Count {all_pids_count}, and/or PID 1 missing)")


# --- 2. 验证父进程访问 ---
print("\n--- [Test 2: Parent Process Access Verification] ---")

try:
    current_process = psutil.Process(my_pid)
    my_ppid = current_process.ppid()
    print(f"This script's Parent PID (PPID) is: {my_ppid}")
    
    print(f"Checking if PPID {my_ppid} can be accessed...")
    try:
        parent = psutil.Process(my_ppid)
        print(f"    SUCCESS: Parent process {my_ppid} is accessible.")
        print(f"    Parent command: {' '.join(parent.cmdline())}")
        print("\n>>> [Test 2 Result]: Parent process is accessible.")
    except psutil.NoSuchProcess:
        print(f"    FAILURE: Parent {my_ppid} NOT FOUND or ACCESS DENIED.")
        print("\n>>> [Test 2 Result]: Security Boundary CONFIRMED.")
        print(f"    (The sandbox prevents accessing parent PID {my_ppid})")
    except psutil.AccessDenied:
        print(f"    FAILURE: Parent {my_ppid} ACCESS DENIED.")
        print("\n>>> [Test 2 Result]: Security Boundary CONFIRMED.")
        print(f"    (The sandbox prevents accessing parent PID {my_ppid})")

except Exception as e:
    print(f"An unexpected error occurred in Test 2: {e}")

print("\n--- [Verification End] ---")