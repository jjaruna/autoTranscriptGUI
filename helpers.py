import os
import numpy as np  # Install with: pip install -U numpy
import regex as re  # Install with: pip install -U regex
import av           # Install with: pip install -U av
import wave
import pytubefix    # Install with: pip install -U pytubefix
from   typing import Iterator, TextIO

# Function: Extract audio from video file and save to .WAV
def extract_audio(infile:str, overwrite:bool=True, silent:bool=True, channels:int=1, sample_rate:int=16000):
    outfile = '.'.join(os.path.basename(infile).split('.')[:-1]) + '.wav'
    if os.path.exists(outfile) and not overwrite:
        print(f"    Audio file already exists. To overwrite, pass overwrite=True")
    else:
        print(f"Extracting audio as: {outfile} ({channels} channel(s) @{sample_rate}Hz)")

        # Open the input video file
        container = av.open(infile)

        # Find the audio stream
        audio_stream = next((stream for stream in container.streams if stream.type == 'audio'), None)

        if not audio_stream:
            raise ValueError("No audio stream found in the input file.")

        # Get duration of audio file
        audio_duration = float(audio_stream.duration * audio_stream.time_base)

        # Open a wave file for output
        with wave.open(outfile, 'wb') as wav_file:
            # Set wave file parameters based on the audio stream
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)  # 16-bit audio
            wav_file.setframerate(sample_rate)

            # Resample and convert audio frames
            resampler = av.audio.resampler.AudioResampler(
                format="s16",
                layout="mono" if channels == 1 else "stereo",
                rate=sample_rate
            )

            # Decode audio frames and write to the wave file
            for packet in container.demux(audio_stream):
                for frame in packet.decode():
                    # Resample the audio frame
                    resampled_frames = resampler.resample(frame)

                    # Convert the frame to raw PCM data
                    for resampled_frame in resampled_frames:
                        pcm_data = resampled_frame.to_ndarray().astype(np.int16).tobytes()
                        wav_file.writeframes(pcm_data)

    # Return filename and duration of extracted Waveform
    return outfile, audio_duration

# Function: Format timestamp for SRT
def format_timestamp(seconds:float, always_include_hours:bool=False) -> str:
    assert seconds >= 0, "non-negative timestamp expected"
    milliseconds = round(seconds * 1000.0)
    hours = milliseconds // 3_600_000
    milliseconds -= hours * 3_600_000
    minutes = milliseconds // 60_000
    milliseconds -= minutes * 60_000
    seconds = milliseconds // 1_000
    milliseconds -= seconds * 1_000
    hours_marker = f"{hours:02d}:" if always_include_hours or hours > 0 else ""
    return f"{hours_marker}{minutes:02d}:{seconds:02d},{milliseconds:03d}"

# Function: Write SRT subtitle
def write_srt(transcript, translation, outfile:TextIO="output.srt", dry_run:bool=False):
    for i, segment in enumerate(transcript, start=1):
        output_text = f"{i}\n"
        output_text += f"{format_timestamp(segment.start, always_include_hours=True)} --> "
        output_text += f"{format_timestamp(segment.end, always_include_hours=True)}\n"
        if len(translation) > 0:
            output_text += f'<font color="#gray">{segment.text.strip().replace("-->", "->")}</font>\n'
            output_text += f'{translation[i-1].get("text").strip().replace("-->", "->")}\n'
        else:
            output_text += f'{segment.text.strip().replace("-->", "->")}\n'
        if dry_run:
            print(output_text, flush=True)
        else:
            print(output_text, file=outfile, flush=True)

# Function: Remove repetitive strings
def remove_repetitions_and_sequences(input_string:str, char_repeats:int=6, seq_repeats:int=3, DEBUG=False) -> str:
    if DEBUG: print(f"Received input: {input_string}")

    # Remove invalid characters
    input_string = input_string.replace("�", "")

    # Handle single-character repetitions first
    single_char_pattern = rf'(.)\1{{{char_repeats},}}'
    result = re.sub(single_char_pattern, lambda m: m.group(1) * char_repeats, input_string)
    if DEBUG: print(f"Removed single-char sequences: {result}")

    # Handle repetitive multi-character sequences
    sequence_pattern = rf'((.+?)\2{{{seq_repeats},}})'
    result = re.sub(sequence_pattern, lambda m: m.group(2) * seq_repeats if len(m.group(2)) > 1 else m.group(0), result)
    if DEBUG: print(f"Removed multi-char sequences: {result}")

    return result

# Split a long sentence at punctuation marks, conservatively ensuring roughly equal lengths
def split_long_sentence(text:str, max_length:int, DEBUG:bool=False) -> list:
    if len(text) <= max_length:
        return [text]

    # Define punctuation marks for potential splitting
    punctuation_marks = r'[,;-।、؛،：]'
    parts = re.split(pattern=punctuation_marks, string=text, flags=re.UNICODE)

    result, current_part = [], ""
    for part in parts:
        if DEBUG: print(f"    Processing part: {part}")
        if len(current_part) + len(part) <= max_length:
            current_part += part
        else:
            if current_part.strip():
                result.append(current_part.strip())
            current_part = part
        if DEBUG: print(f"    Current part: {current_part}")

    if current_part.strip():
        result.append(current_part.strip())

    # Ensure no individual part exceeds max_length by splitting at spaces conservatively
    final_result = []
    for part in result:
        if len(part) > max_length:
            words = part.split()
            current = []
            for word in words:
                if len(" ".join(current) + " " + word) <= max_length:
                    current.append(word)
                else:
                    final_result.append(" ".join(current).strip())
                    current = [word]
            if current:
                final_result.append(" ".join(current).strip())
        else:
            final_result.append(part)

    return final_result

# Function: Split and merge segments based on international punctuation, sentence completion, and sentence length
def adjust_segments(segments, lookahead_segments:int=3, max_sentence_length:int=100, DEBUG:bool=False):
    # Check if the text ends with a sentence-ending punctuation mark
    def is_sentence_complete(text):
        return bool(re.search(r'[.!?।።。！？¿¡](?=\s|$)', text.strip()))

    result_segments = []
    buffer_text = []
    buffer_start = None
    processed_segments = set()  # Tracks processed segments to avoid duplication

    for i, segment in enumerate(segments):
        if i in processed_segments:
            continue  # Skip already processed segments

        buffer_text = []
        buffer_start = None

        # Gather text from the current segment and lookahead
        for j in range(i, min(i + lookahead_segments + 1, len(segments))):
            if j in processed_segments:
                continue

            current_segment = segments[j]
            for word in current_segment.words:
                word_text = word.word.strip()
                word_start = round(word.start, 2)
                word_end = round(word.end, 2)

                if buffer_start is None:
                    buffer_start = word_start
                buffer_text.append((word_text, word_start, word_end))

            processed_segments.add(j)

        # Combine buffer into text
        combined_text = " ".join([w[0] for w in buffer_text]).strip()
        if DEBUG: print(f"Combined text: {combined_text}")

        # Split into sentences at end-of-sentence punctuation
        sentences = re.split(r'(?<=[.!?।።。！？¿¡])\s+', combined_text)
        sentence_start = buffer_start

        for sentence in sentences:
            if not sentence.strip():
                continue

            # Extract start and end times for the sentence
            sentence_words = [w for w in buffer_text if w[0] in sentence]
            sentence_start = sentence_words[0][1]
            sentence_end = sentence_words[-1][2]

            # Split long sentences if necessary
            if DEBUG: print(f"Current sentence: {sentence}")
            result_segments.append({
                "start": sentence_start,
                "end": sentence_end,
                "text": sentence
            })
            """
            split_sentences = split_long_sentence(text=sentence.strip(), max_length=max_sentence_length, DEBUG=DEBUG)
            for split_sentence in split_sentences:
                result_segments.append({
                    "start": sentence_start,
                    "end": sentence_end,
                    "text": split_sentence
                })
            """

    return result_segments

def cleanup_text(segment:dict) -> dict:
    input_string = segment.text.strip()
    # Remove prefix "-" at start of lines
    input_string = re.sub(r"^- ", "", input_string, flags=re.MULTILINE)
    output_string = remove_repetitions_and_sequences(input_string)
    segment.text = output_string
    return segment

def remove_dup_segments(segments):
    if not segments:  # Handle empty list
        return []

    result = [segments[0]]  # Initialize with the first element
    for i in range(1, len(segments)):
        if segments[i].text != segments[i - 1].text:  # Compare with the previous element
            result.append(segments[i])
    return result

def adjust_duration(segment):
    length_duration = round(float(segment.end) - float(segment.start), 2)
    length_text = len(segment.text)
    length_max = round(max(length_text / 3, 3), 2)
    if length_duration > length_max:
        segment.end = round(float(segment.start) + length_max, 2)
        print(f"    Shortened length: {round(float(segment.start), 2)} --> {round(float(segment.end), 2)} ({length_duration} -> {length_max}) {segment.text}")
    """
    length_min = min(length_text / 4, 10)
    if length_duration < length_min:
        segment["end"] = float(segment.get("start")) + length_min
        print(f"Increased length: {segment.get("start")} --> {segment.get("end")} ({length_duration} -> {length_min}) {segment.get("text")}")
    """
    return segment

def get_youtube_video(url:str) -> str:
    # Barack Obama 2004 DNC Speech: https://www.youtube.com/watch?v=ueMNqdB1QIE
    # Teddy Roosevelt 1912 Speech: https://www.youtube.com/watch?v=uhlzdjPGxrs
    if "youtube" in url.replace(".",""):
        yt = pytubefix.YouTube(url)#, on_progress_callback=on_progress)
        print(f"Downloading Youtube video: {yt.title}")

        ys = yt.streams.get_highest_resolution()
        outfile = f"{yt.title}.mp4"
        filepath = ys.download(filename=outfile)
    else:
        print(f"URL {url} is not a valid YouTube video")
        outfile = ""
    return outfile
