$env:AUDIOBOOKFORGE_FORCE_CPU="0"
$env:AUDIOBOOKFORGE_USE_TENSORRT="0"
$env:AUDIOBOOKFORGE_CUDA_ONLY="1"
$env:AUDIOBOOKFORGE_SUPPRESS_ORT_WARNINGS="1"
$env:AUDIOBOOKFORGE_ADD_SYSTEM_CUDA_DLL_PATH="0"

python benchmark_e2e_single_chapter.py "C:\Users\mateo\Desktop\AudioBookForge\library\Dennett,_Daniel_Clement_-_Intuition_Pumps_and_Other_Tools_for_Thinking\content\ch_004.txt" --voice M3 --tts-max-chars 800 --whisper-model small --whisper-batch-size 16 --whisper-compute-type int8 --device cuda --output-wav "benchmark_e2e_ch004.wav" --output-json "benchmark_e2e_ch004.json" --report-json "benchmark_e2e_ch004_report.json"
