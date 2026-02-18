import argparse
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog='autosub.py',
        description='AutoSub automatically extracts subtitles from video or audio files using OpenAI Whisper',
    )
    parser.add_argument('filename', help="Path and name of the video or audio file to extract from, or URL of YouTube video")
    parser.add_argument('-l', '--language', help="Override language of video file, e.g. en, ja, ko, zh")
    parser.add_argument('-t', '--translate', help="Automatically translate subtitles to English", action='store_true')
    parser.add_argument('-o', '--openai', help="Use OpenAI API to translate subtitles, keeping transcription", action='store_true')
    parser.add_argument('--model', help="Override the Whisper model used")
    parser.add_argument('--temperature', help="Override the temperature used by Whisper")
    parser.add_argument('--beamsize', help="Override the beam size used by Whisper")
    parser.add_argument('--noprev', help="Override the condition_on_previous_text parameter to False", action='store_true')
    parser.add_argument('--threshold', help="Override the threshold used for VAD")
    parser.add_argument('--debug', help="Add debug logs to program execution", action='store_true')
    parser.add_argument('--keep', help="Keep WAV file created during process", action='store_true')
    args = parser.parse_args()

    print("Importing modules")
    # Import Python modules
    import sys
    import pickle
    import shutil
    import time
    import os
    import io
    import gc
    from   faster_whisper import WhisperModel  
    from   translate import process_translation
    from   helpers import extract_audio, get_youtube_video, write_srt
    from   helpers import adjust_segments, cleanup_text, remove_dup_segments, adjust_duration
    sys.stdout.reconfigure(line_buffering=True)
    # Set debug mode
    DEBUG = args.debug
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1" #new
    filename = args.filename
    if "http" in filename:
        print("Attempting to download YouTube video")
        filename = get_youtube_video(filename)
    else:
        if not os.path.exists(filename):
            print("ERROR: File not found")
            exit()
        else:
            print(f"Processing video: {os.path.basename(filename)}")

    audio_file, audio_duration = extract_audio(filename)
    # NOTE: 
    whisper_models = ['tiny', 'base', 'small', 'medium', 'large-v1', 'large-v2', 'large-v3', 'large-v3-turbo']
    DEFAULT_MODEL = 'large-v3'
    if args.model:
        model_name = args.model
        if model_name not in whisper_models:
            print(f"{model_name} is not a valid Whisper model. Defaulting to {DEFAULT_MODEL}")
            model_name = DEFAULT_MODEL
    else:
        model_name = DEFAULT_MODEL
        print(f"Loading Whisper model: {model_name}")

# Auto
    try:
        import torch
        has_cuda = torch.cuda.is_available()
    except Exception:
        has_cuda = False

    if has_cuda:
        device = "cuda"
        compute_type = "float16"   # rápido en GPU
    else:
        device = "cpu"
        compute_type = "int8"      # liviano y rápido en CPU (ideal para Windows sin GPU)

    print(f"Using device={device} | compute_type={compute_type}")
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    # Set default Whisper options
    options = {"task": "transcribe"}

    # Automatically detect language if not overridden
    if args.language:
        options['language'] = args.language

    # Check if user wants to use OpenAI API to translate subtitles
    OPENAI = args.openai
    # Check if user wants to translate instead of transcribe
    if args.translate:
        if not OPENAI:
            options['task'] = "translate"

    # Set Whisper and VAD parameters
    TEMPERATURE = float(args.temperature) if args.temperature else 0
    BEAMSIZE = int(args.beamsize) if args.beamsize else 10
    PREVTEXT = not args.noprev
    VAD_THRESHOLD = float(args.threshold) if args.threshold else 0.5 #0.5 STANDARD
    WORD_TIMESTAMPS = True
    print(f"Using options: Temperature {TEMPERATURE}, Beam Size {BEAMSIZE}, Prev-Text {PREVTEXT}, VAD Threshold {VAD_THRESHOLD}")

    print("Extracting subtitles")
    # Initialize timer for transcription
    time_start = time.perf_counter()
    vad_params = dict(
        threshold=VAD_THRESHOLD,       # Default 0.5. Speech threshold. Silero VAD outputs speech probabilities for each audio chunk, probabilities ABOVE this value are considered as SPEECH.
        #neg_threshold=0.15,           # Default None. Silence threshold for determining the end of speech. If a probability is lower than neg_threshold, it is always considered silence.
        #min_speech_duration_ms=0,     # Default 0. Final speech chunks shorter min_speech_duration_ms (in milliseconds) are thrown out
        #max_speech_duration_s=1.0,    # Default float("inf"). Chunks longer than max_speech_duration_s (in seconds) will be split at the timestamp of the last silence that lasts more than 100ms (if any)
        #min_silence_duration_ms=100,  # Default 2000. In the end of each speech chunk wait for min_silence_duration_ms (in milliseconds) before separating it
        #speech_pad_ms=0,              # Default 400. Final speech chunks are padded by speech_pad_ms each side
    )
    segments, info = model.transcribe(
        audio=audio_file,
        language=options.get("language"),
        task=options.get("task"),
        beam_size=BEAMSIZE,       # Default 5. Beam size to use for decoding.
        #best_of=2,               # Default 5. Number of candidates when sampling with non-zero temperature.
        #patience=2,              # Default 1. Beam search patience factor.
        repetition_penalty=1.5,   # Default 1. Penalty applied to the score of previously generated tokens (set > 1 to penalize)
        #no_repeat_ngram_size=2,  # Default 0. Prevent repetitions of ngrams with this size (set 0 to disable)
        log_progress=False,
        temperature=TEMPERATURE,  # Temperature for sampling. If a list or tuple is passed, only the first value is used
        condition_on_previous_text=PREVTEXT,
        #suppress_tokens=[], # Default [-1]
        word_timestamps=WORD_TIMESTAMPS,  # Retrieve timestamps for each word
        vad_filter=True,  # The library integrates the Silero VAD model to filter out parts of the audio without speech
        vad_parameters=vad_params,  # Customize VAD parameters
    )
    print("Detected language '%s' with probability %f" % (info.language, info.language_probability))

    # NOTE: segments is a generator so the transcription only starts when you iterate over it
    # The transcription can be run to completion by gathering the segments in a list or a for loop
    # segments = list(segments)  # The transcription will actually run here.
    print("Transcribing text")
    list_transcribe = []
    count_duplicates = 0
    prev_segment = ""
    for segment in segments:
        if info.language in ["ja"] and not args.translate:
            segment.text = segment.text.replace(" ", "")  # Remove additional spaces
        
        text = " ".join(segment.text.strip().split()) # NEW
        print(f"    {segment.start} --> {segment.end} {text}")
        
        if prev_segment == text:
            count_duplicates += 1
        else:
            count_duplicates = 0
        
        if count_duplicates > 10:
            print("Possible hallucination detected. Skipping segment.")
            continue
    
        prev_segment = text
        segment.text = text  # CLEAN VERSION
        #if WORD_TIMESTAMPS:
        #    for word in segment.words:
        #        print(f"    [{round(word.start, 2)} -> {round(word.end, 2)}] {word.word}")
        list_transcribe.append(segment)
    print(f"Transcribed {len(list_transcribe)} segments")
    # Unload Whisper model
    model.model.unload_model()
    del model
    gc.collect()

    # Adjust segments to merge incomplete sentences and split at punctuation marks
    #print("Post-processing segments")
    #list_transcribe_adj = adjust_segments(list_transcribe)
    #_ = [print(f"    {seg.get('start')} --> {seg.get('end')} {seg.get('text')}") for seg in list_transcribe_adj]

    # HACK: Remove repetitions caused by Whisper hallucination
    list_transcribe_clean = [cleanup_text(item) for item in list_transcribe]
    # HACK: Remove duplicate segments caused by Whisper hallucination
    #list_transcribe_clean = remove_dup_segments(list_transcribe_clean)
    # HACK: Shorten long durations caused by Whisper hallucination
    list_transcribe_clean = [adjust_duration(item) for item in list_transcribe_clean]
    if len(list_transcribe) != len(list_transcribe_clean):
        print(f"Cleaned up to {len(list_transcribe)} -> {len(list_transcribe_clean)} segments")
    # End timer and calculation time taken
    time_end = time.perf_counter()
    time_elapsed = time_end - time_start
    print(f"Input file of {audio_duration:.2f} seconds transcribed in {time_elapsed:.2f} seconds.")

    # Store transcription as Pickle in debug mode
    if DEBUG:
        with open(file="list_transcribe.pkl", mode="wb") as f:
            pickle.dump(obj=list_transcribe_clean, file=f, protocol=pickle.HIGHEST_PROTOCOL)
            print("    Pickled to list_transcribe.pkl for debugging")

    if not args.keep:
        print(f"Deleting audio file: {audio_file}")
        os.remove(audio_file)

    # Translate subtitles using OpenAI API
    list_translate = []
    if OPENAI:
        # Initialize timer for translation
        time_start = time.perf_counter()
        list_translate = process_translation(list_original=list_transcribe_clean, DEBUG=DEBUG)
        # Check to see if translation succeeded
        if len(list_transcribe_clean) != len(list_translate):
            print("ERROR: Translation failed")
            sys.exit(-1)
        # End timer and calculation time taken
        time_end = time.perf_counter()
        time_elapsed = time_end - time_start
        print(f"Translation completed in {time_elapsed:.2f} seconds.")

    srt_file = outfile = '.'.join(os.path.basename(filename).split('.')[:-1]) + '.srt'
    with open(srt_file, "w", encoding="utf-8") as srt:
        write_srt(list_transcribe_clean, list_translate, outfile=srt)
    print(f"Wrote subtitle file to: {srt_file}")
    if not "http" in filename:
        file_dir = os.path.dirname(os.path.abspath(filename))
        if file_dir != os.getcwd():
            print(f"Moving subtitle file to: {file_dir}")
            shutil.copy2(srt_file, file_dir)
            os.remove(srt_file)

# NOTE: ffmpeg needs to be installed on the system first
# On Windows, install with: choco install ffmpeg

# NOTE: torch needs to be in installed
# pip install -U torch torchaudio --index-url https://download.pytorch.org/whl/cu124
