# Restore main Cadence main venv for Supertonic TTS stability.
# Run inside: .\venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install --force-reinstall "numpy==1.26.4"
python -m pip install --force-reinstall "torch==2.6.0+cu124" "torchvision==0.21.0+cu124" "torchaudio==2.6.0+cu124" --index-url https://download.pytorch.org/whl/cu124

python -c "import numpy, torch; print('numpy', numpy.__version__); print('torch', torch.__version__, 'cuda', torch.version.cuda, 'cuda_available', torch.cuda.is_available())"
