import subprocess
import sys
from pathlib import Path

from watchfiles import watch


def start_app():
    return subprocess.Popen([sys.executable, "main.py"])


def should_restart(changed_paths):
    for _change, path in changed_paths:
        if Path(path).suffix == ".py":
            return True
    return False


def main():
    process = start_app()
    try:
        for changes in watch(".", recursive=True):
            if not should_restart(changes):
                continue
            print("Detected Python file change. Restarting app...")
            process.terminate()
            process.wait()
            process = start_app()
    except KeyboardInterrupt:
        pass
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()


if __name__ == "__main__":
    main()
