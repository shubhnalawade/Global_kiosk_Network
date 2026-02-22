"""
run_system.py
=============
System launcher for the Global Kiosk Network.

Each service gets its OWN console window (so logs are separated).
Closing this launcher window OR pressing Ctrl+C will STOP all three services.

Services:
  - Cloud Server       (port 5000)  cloud_server/app.py
  - Kiosk Server       (port 5001)  kiosk/app.py
  - Kiosk Sync Service             kiosk/kiosk_sync.py
"""

import subprocess
import sys
import time
import os


def run_system():
    root_dir = os.path.dirname(os.path.abspath(__file__))

    services = [
        {
            "description": "Cloud Server",
            "path": os.path.join(root_dir, "cloud_server", "app.py"),
            "cwd":  os.path.join(root_dir, "cloud_server"),
        },
        {
            "description": "Kiosk Server",
            "path": os.path.join(root_dir, "kiosk", "app.py"),
            "cwd":  os.path.join(root_dir, "kiosk"),
        },
        {
            "description": "Kiosk Sync Service",
            "path": os.path.join(root_dir, "kiosk", "kiosk_sync.py"),
            "cwd":  os.path.join(root_dir, "kiosk"),
        },
    ]

    print("### GLOBAL KIOSK NETWORK - SYSTEM RUNNER ###")
    print(f"Root Directory : {root_dir}")
    print(f"Python         : {sys.executable}")
    print("-" * 50)

    processes = []

    for svc in services:
        print(f"Starting {svc['description']}...")
        p = subprocess.Popen(
            [sys.executable, svc["path"]],
            cwd=svc["cwd"],
            # Each service opens in its own console window for separate logs.
            # We still hold the process object so we can terminate it later.
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        processes.append((svc["description"], p))
        print(f"  -> {svc['description']} started (PID: {p.pid})")
        time.sleep(1)   # Allow each service a moment to bind its port

    print("-" * 50)
    print("All services running in separate windows.")
    print(">>> Press Ctrl+C here to STOP all services at once. <<<")
    print("-" * 50)
    print()
    print("╔════════════════════════════════════════════════════════╗")
    print("║   GLOBAL KIOSK NETWORK - SYSTEM ONLINE               ║")
    print("╠════════════════════════════════════════════════════════╣")
    print("║                                                        ║")
    print("║  🌐 CONTROL CENTER:                                  ║")
    print("║     http://localhost:5001                            ║")
    print("║                                                        ║")
    print("║  🖨️  KIOSK PAGE:                                      ║")
    print("║     http://localhost:5001/kiosk/TB001                ║")
    print("║                                                        ║")
    print("║  📱 UPLOAD PAGE (Mobile):                            ║")
    print("║     http://localhost:5000/upload?kiosk_id=TB001      ║")
    print("║                                                        ║")
    print("║  ✨ FEATURES:                                         ║")
    print("║     • Upload PDFs and manage queue                   ║")
    print("║     • Set print settings for each document           ║")
    print("║     • Live price calculation                         ║")
    print("║     • PDF preview with zoom & rotate                 ║")
    print("║     • Owner authentication & dashboard               ║")
    print("║                                                        ║")
    print("╚════════════════════════════════════════════════════════╝")
    print()

    # -----------------------------------------------------------------------
    # Wait until Ctrl+C or this window is closed, then kill all children.
    # -----------------------------------------------------------------------
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    print("\n[STOP] Shutting down all services...")

    for name, p in processes:
        try:
            p.terminate()
            p.wait(timeout=5)
            print(f"  [OK] {name} stopped (PID: {p.pid})")
        except Exception as e:
            print(f"  [WARN] Could not stop {name} cleanly ({e}), forcing kill...")
            try:
                p.kill()
            except Exception:
                pass

    print("\nAll services stopped. Run 'python run_system.py' to restart.\n")


if __name__ == "__main__":
    run_system()
