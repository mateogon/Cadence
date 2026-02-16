
import os
import sys

print("Testing CUDA Detection Logic...")

# copy-pasted logic from generate_audiobook_supertonic.py
CUDA_BASE_PATH = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
if os.path.exists(CUDA_BASE_PATH) and hasattr(os, 'add_dll_directory'):
    print(f"CUDA_BASE_PATH found: {CUDA_BASE_PATH}")
    # Find all v* directories
    cuda_dirs = []
    try:
        for entry in os.scandir(CUDA_BASE_PATH):
            if entry.is_dir() and entry.name.startswith("v"):
                cuda_dirs.append(entry.path)
    except OSError as e:
        print(f"⚠️  Error scanning CUDA directory: {e}")

    # Sort reverse alphabetically (e.g., v12.8 > v12.4)
    cuda_dirs.sort(reverse=True)
    print(f"Found CUDA directories: {cuda_dirs}")
    
    cuda_found = False
    for cuda_dir in cuda_dirs:
        bin_path = os.path.join(cuda_dir, "bin")
        if os.path.exists(bin_path):
            try:
                # Mocking add_dll_directory call for visual confirmation (or just calling it)
                os.add_dll_directory(bin_path)
                print(f"✅ Added CUDA DLL path: {bin_path}")
                cuda_found = True
                break # Stop after adding the latest valid one
            except OSError as e:
                print(f"⚠️  Failed to add CUDA DLL path: {bin_path} -> {e}")
    
    if not cuda_found:
         print(f"⚠️  No valid CUDA v*\\bin directories found in {CUDA_BASE_PATH}")
elif os.name == 'nt':
     print("ℹ️  CUDA base directory not found or add_dll_directory not supported.")
else:
    print("Not running on Windows NT.")
