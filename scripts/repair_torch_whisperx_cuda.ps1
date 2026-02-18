# Deprecated for mixed TTS+WhisperX envs.
# WhisperX (numpy>=2.1, torch~=2.8) conflicts with Supertonic (numpy<2.0).
# Use:
#   - repair_main_tts_env.ps1      (main env for Supertonic)
#   - setup_whisperx_gpu_env.ps1   (separate env for WhisperX GPU)

python -m pip uninstall -y torch torchvision torchaudio
python -m pip install --upgrade pip
python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Quick sanity check
python -c "import torch; print('torch', torch.__version__); print('cuda_available', torch.cuda.is_available()); print('cuda', torch.version.cuda)"
