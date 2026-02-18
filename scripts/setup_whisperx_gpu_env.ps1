# Create a dedicated WhisperX GPU env (separate from main TTS env).

python -m venv venv_whisperx
.\venv_whisperx\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install whisperx

# Replace CPU Torch wheels with CUDA wheels compatible with WhisperX torch~=2.8
python -m pip uninstall -y torch torchvision torchaudio
python -m pip install "torch==2.8.0+cu124" "torchvision==0.23.0+cu124" "torchaudio==2.8.0+cu124" --index-url https://download.pytorch.org/whl/cu124

python -c "import torch; print('torch', torch.__version__, 'cuda', torch.version.cuda, 'cuda_available', torch.cuda.is_available())"
python -c "import whisperx; print('whisperx import ok')"
