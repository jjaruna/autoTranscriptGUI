# AutoTranscript GUI 🎙️

**AutoTranscript** is a powerful, GPU-accelerated subtitle generator built on top of OpenAI's Whisper model. It features both a **command-line interface (CLI)** and a beautiful **CustomTkinter-based GUI** for users who prefer a graphical workflow.

Supports:
- Languages such as: English, Chinese, Japanese, Korean.
- Local audio/video files.
- Translate or transcribe YouTube videos using only the link.
- Subtitle translation to English.
- OpenAI API (for higher quality translations) NOT AVAILABLE 

---

## ✨ Features

- 🖥️ Full-featured **GUI with progress tracking**, real-time logs.
- 📜 Generate `.srt` subtitle files from media files
- 🌍 Supports multilingual transcription and optional **translation to English**
- 🧠 Uses [Faster-Whisper](https://github.com/guillaumekln/faster-whisper) for fast GPU-accelerated transcription

---
## YOUTUBE TUTORIAL IN SPANISH

(https://www.youtube.com/watch?v=dB6D1i1BjXc)

---
## 📸 GUI Preview

> ![image](https://github.com/user-attachments/assets/d328dff2-4d82-485c-95b8-162405a3e856)

---

## 🧩 Requirements

- Python 
- NVIDIA GPU with CUDA (recommended)
- Visual C++ Redistributable 14

---
## Installation for Releases 

 - Extract the .rar file.
 - Go to the app folder.
 - At the top of the path bar, type cmd.
 - In the console, type: pip install -r requirements.txt.
 - Go back to the .bat file and run it.
---

## 📦 Installation

```bash
git clone https://github.com/jjaruna/autoTranscriptGUI.git
cd autoTranscriptGUI
pip install -r requirements.txt
```
---

## 🚀 Launch the GUI

```bash
python AutoTranscriptGUI.py
```
### 🔍 Whisper Model Comparison Summary

| Model               | VRAM (Min)    | ⚙️ Performance        | 🎯 Use Case                                               | 🌐 Translate into English |
|--------------------|---------------|------------------------|-----------------------------------------------------------|--------------------------|
| `tiny`             | ≥ 1 GB        | ⚡ Very Fast            | Quick tests, low-resource devices                         | ✅                        |
| `base`             | ≥ 2 GB        | ⚡ Fast                 | Simple transcriptions, short audio                        | ✅                        |
| `small`            | ≥ 4 GB        | ⚖️ Balanced            | Decent accuracy and speed for general use                | ✅                        |
| `medium`           | ≥ 8 GB        | 🕒 Slower              | High-quality results for longer files                    | ✅                        |
| `large-v1`         | ≥ 10 GB       | 🐢 Slower              | Older but still strong performer                         | ✅                        |
| `large-v2`         | ≥ 10 GB       | 🐢 Slower              | More robust, especially with noisy inputs                | ✅                        |
| `large-v3`         | ≥ 12 GB       | 🐌 Slowest             | Highest accuracy offline, latest version                 | ✅                        |
| `large-v3-turbo`   | ≥ 8–10 GB     | ⚡ Fastest             | High-speed, high-accuracy, great multilingual support     | ❌                        |


# 🧠 Recommendation

After testing the `large-v3-turbo` model more than 10 times, I can confidently say it is the **fastest** and **most accurate** among all Whisper models included in this app.

🖥️ My system has **4GB of VRAM**, and despite being under the recommended VRAM for large models, `large-v3-turbo` still performed exceptionally well.

⚠️ **Note:** Your experience may vary depending on your GPU and available VRAM. Use this recommendation as a reference, **not a guarantee**. If you encounter performance issues, try smaller models like `medium` or `small`.

---

## 🖥️ CLI Mode (Optional)

You can still use the command-line version via `autosub.py`:

```bash
python autosub.py myvideo.mp4 -l ja --translate --model base
```

### CLI Options

| Option              | Description |
|---------------------|-------------|
| `filename`          | File path |
| `-l`, `--language`  | Force language (e.g. `en`, `es`, `zh`) |
| `-t`, `--translate` | Translate to English |
| `-o`, `--openai`    | Use OpenAI API |
| `--model`           | Whisper model to use |
| `--debug`           | Enable debug mode |
| `--keep`            | Keep intermediate WAV file |

---

## 📝 Output

- Subtitles are saved as `.srt` files in the same folder as your media.
- If translated, original and translated text will be preserved.

---

## 🧪 Example GUI Workflow

1. Open GUI
2. Select video/audio file
3. Choose language and Whisper model
4. (Optional) Enable "Translate to English"
5. Click **Start Transcription**

---

## 🙏 Credits

- Built with [OpenAI Whisper](https://github.com/openai/whisper)
- Powered by [Faster-Whisper](https://github.com/guillaumekln/faster-whisper)
- GUI built with [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)
- Thank you General Koi, for the great help in testing and reviewing the Japanese transcripts.

---

## 📄 License

MIT License — free for personal and commercial use.

