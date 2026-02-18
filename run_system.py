import subprocess
import sys
import time
import os

def run_system():
    # Define the scripts to run and their working directories relative to the root
    # Using absolute paths for scripts to avoid ambiguity
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

    processes = []

    print("### GLOBAL KIOSK NETWORK - SYSTEM RUNNER ###")
    print(f"Root Directory: {root_dir}")
    print(f"Python Executable: {sys.executable}")
    print("-" * 50)

    try:
        for script in scripts:
            print(f"Starting {script['description']}...")
            
            # Use sys.executable to ensure we use the same Python interpreter
            p = subprocess.Popen(
                [sys.executable, script['path']],
                cwd=script['cwd'],
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
            )
            processes.append(p)
            print(f"Started {script['description']} (PID: {p.pid})")

        print("-" * 50)
        print("All services are running in separate windows.")
        print("Press Ctrl+C in this window to stop all services.")

        while True:
            time.sleep(1)
            # Check if any process has exited
            all_dead = True
            for p in processes:
                if p.poll() is None:
                    all_dead = False
                    break
            if all_dead:
                print("All services have stopped.")
                break

    except KeyboardInterrupt:
        print("\nStopping all services...")
    finally:
        for p in processes:
            if p.poll() is None:
                print(f"Terminating process {p.pid}...")
                p.terminate()
        print("System terminated.")

if __name__ == "__main__":
    run_system()
