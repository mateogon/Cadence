$env:AUDIOBOOKFORGE_FORCE_CPU="0"
$env:AUDIOBOOKFORGE_USE_TENSORRT="0"
$env:AUDIOBOOKFORGE_CUDA_ONLY="1"
$env:AUDIOBOOKFORGE_SUPPRESS_ORT_WARNINGS="1"

# One-chunk and multi-chunk sweep (same file, same worker count).
python benchmark_supertonic_single_file_chunks.py "C:\Users\mateo\Desktop\AudioBookForge\library\Dennett,_Daniel_Clement_-_Intuition_Pumps_and_Other_Tools_for_Thinking\content\ch_004.txt" --voice M3 --max-chars 5000 --workers "1" --repeats 2 --output-csv "benchmark_ch004_len_5000.csv"
python benchmark_supertonic_single_file_chunks.py "C:\Users\mateo\Desktop\AudioBookForge\library\Dennett,_Daniel_Clement_-_Intuition_Pumps_and_Other_Tools_for_Thinking\content\ch_004.txt" --voice M3 --max-chars 1600 --workers "1" --repeats 2 --output-csv "benchmark_ch004_len_1600.csv"
python benchmark_supertonic_single_file_chunks.py "C:\Users\mateo\Desktop\AudioBookForge\library\Dennett,_Daniel_Clement_-_Intuition_Pumps_and_Other_Tools_for_Thinking\content\ch_004.txt" --voice M3 --max-chars 1000 --workers "1" --repeats 2 --output-csv "benchmark_ch004_len_1000.csv"
python benchmark_supertonic_single_file_chunks.py "C:\Users\mateo\Desktop\AudioBookForge\library\Dennett,_Daniel_Clement_-_Intuition_Pumps_and_Other_Tools_for_Thinking\content\ch_004.txt" --voice M3 --max-chars 800 --workers "1" --repeats 2 --output-csv "benchmark_ch004_len_800.csv"
python benchmark_supertonic_single_file_chunks.py "C:\Users\mateo\Desktop\AudioBookForge\library\Dennett,_Daniel_Clement_-_Intuition_Pumps_and_Other_Tools_for_Thinking\content\ch_004.txt" --voice M3 --max-chars 500 --workers "1" --repeats 2 --output-csv "benchmark_ch004_len_500.csv"
python benchmark_supertonic_single_file_chunks.py "C:\Users\mateo\Desktop\AudioBookForge\library\Dennett,_Daniel_Clement_-_Intuition_Pumps_and_Other_Tools_for_Thinking\content\ch_004.txt" --voice M3 --max-chars 300 --workers "1" --repeats 2 --output-csv "benchmark_ch004_len_300.csv"
