import os
import sys


def print_header(title):
    print(f"\n=== {title} ===")


def check_imports():
    print_header("Core Imports")
    try:
        print("Importing supertonic...")
        import supertonic

        print(f"Supertonic version: {supertonic.__version__}")
    except Exception as exc:
        print(f"Supertonic import failed: {exc}")

    try:
        print("Importing whisperx...")
        import whisperx

        print("WhisperX imported successfully")
    except Exception as exc:
        print(f"WhisperX import failed: {exc}")

    try:
        import numpy

        print(f"Numpy version: {numpy.__version__}")
    except Exception as exc:
        print(f"Numpy import failed: {exc}")


def check_torch_cuda():
    print_header("Torch / CUDA")
    try:
        import torch

        print(f"Python: {sys.version.split()[0]}")
        print(f"Torch Version: {torch.__version__}")
        print(f"CUDA Available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"Current Device: {torch.cuda.current_device()}")
            print(f"Device Name: {torch.cuda.get_device_name(0)}")
        else:
            print("No CUDA device detected by Torch.")
    except Exception as exc:
        print(f"Torch check failed: {exc}")


def check_windows_cuda_dll_path():
    print_header("Windows CUDA DLL Path")
    cuda_base = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
    if not os.name == "nt":
        print("Not running on Windows NT.")
        return
    if not os.path.exists(cuda_base) or not hasattr(os, "add_dll_directory"):
        print("CUDA base directory not found or add_dll_directory unavailable.")
        return

    print(f"CUDA_BASE_PATH found: {cuda_base}")
    cuda_dirs = []
    try:
        for entry in os.scandir(cuda_base):
            if entry.is_dir() and entry.name.startswith("v"):
                cuda_dirs.append(entry.path)
    except OSError as exc:
        print(f"Error scanning CUDA directory: {exc}")
        return

    cuda_dirs.sort(reverse=True)
    print(f"Found CUDA directories: {cuda_dirs}")
    for cuda_dir in cuda_dirs:
        bin_path = os.path.join(cuda_dir, "bin")
        if not os.path.exists(bin_path):
            continue
        try:
            os.add_dll_directory(bin_path)
            print(f"Added CUDA DLL path: {bin_path}")
            return
        except OSError as exc:
            print(f"Failed to add CUDA DLL path: {bin_path} -> {exc}")
    print(f"No valid CUDA v*/bin directories found in {cuda_base}")


if __name__ == "__main__":
    check_imports()
    check_torch_cuda()
    check_windows_cuda_dll_path()
