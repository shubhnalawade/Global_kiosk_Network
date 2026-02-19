import subprocess
import sys
import time
import os

def run_system():
    root_dir = os.path.dirname(os.path.abspath(__file__))

    scripts = [
        {
            "description": "Cloud Server",
            "path": os.path.join(root_dir, "cloud_server", "app.py"),
            "cwd": os.path.join(root_dir, "cloud_server")
        },
        {
            "description": "Kiosk Server",
            "path": os.path.join(root_dir, "kiosk", "app.py"),
            "cwd": os.path.join(root_dir, "kiosk")
        },
        {
            "description": "Kiosk Sync Service",
            "path": os.path.join(root_dir, "kiosk", "kiosk_sync.py"),
            "cwd": os.path.join(root_dir, "kiosk")
        },
    ]

    print("### GLOBAL KIOSK NETWORK - SYSTEM RUNNER ###")
    print(f"Root Directory: {root_dir}")
    print(f"Python: {sys.executable}")
    print("-" * 50)

    pids = []

    for script in scripts:
        print(f"Starting {script['description']}...")

        # CREATE_NEW_CONSOLE opens a new window per service.
        # We do NOT attach processes to this launcher — they are independent.
        p = subprocess.Popen(
            [sys.executable, script["path"]],
            cwd=script["cwd"],
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        pids.append(p.pid)
        print(f"  -> {script['description']} started (PID: {p.pid})")
        time.sleep(1)  # Wait a moment for each service to bind its port

    print("-" * 50)
    print("All services launched in separate windows.")
    print(f"PIDs: {pids}")
    print("NOTE: Close the individual service windows to stop a specific service.")
    print("      Do NOT close this window using Ctrl+C (that would terminate children).")
    print("      You may minimize this window safely.")

    # Keep alive without monitoring — services are independent
    # Use a simple infinite wait so this window can stay open as reference
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nLauncher closed. Services continue running in their own windows.")

if __name__ == "__main__":
    run_system()
