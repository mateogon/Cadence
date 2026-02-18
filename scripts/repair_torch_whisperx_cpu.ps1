# Reinstall Torch CPU build in the active venv to make WhisperX run without CUDA DLL issues.
python -m pip uninstall -y torch torchvision torchaudio
python -m pip install --upgrade pip
python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Optional: reinstall WhisperX dependencies in case of resolver conflicts.
python -m pip install --upgrade whisperx
