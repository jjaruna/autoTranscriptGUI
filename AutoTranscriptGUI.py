import customtkinter as ctk
import tkinter.filedialog as fd
import tkinter.messagebox as mb
import torch
import threading
import subprocess
import os
import queue
import re
import time
import sys
import ctypes
from datetime import datetime, timedelta
from dotenv import load_dotenv

openai_config_window = None
whisper_models = ['tiny', 'base', 'small', 'medium', 'large-v1', 'large-v2', 'large-v3', 'large-v3-turbo']
whisper_languages = ['auto', 'en', 'zh', 'ja', 'ko']

load_dotenv()
current_openai_key = os.getenv("OPENAI_API_KEY", "")
current_openai_model = os.getenv("OPENAI_MODEL", "gpt-4")

transcription_process = None

class TranscriptionTracker:
    def __init__(self):
        self.reset()
        
    def reset(self):
        self.start_time = None
        self.estimated_total_time = None
        self.total_segments = 0
        self.processed_segments = 0

    def start(self):
        self.reset()
        self.start_time = time.time()

    def update_segments(self, total, processed):
        self.total_segments = total
        self.processed_segments = processed

    def get_estimate(self):
        if self.processed_segments > 0 and self.start_time:
            elapsed = time.time() - self.start_time
            estimated_total = (elapsed / self.processed_segments) * self.total_segments
            remaining = max(0, estimated_total - elapsed)
            return timedelta(seconds=int(remaining))
        return None

tracker = TranscriptionTracker()

def get_vram():
    if torch.cuda.is_available():
        return torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    return 0

def suggest_model():
    vram = get_vram()
    if vram >= 20: return 'large-v3'
    elif vram >= 10: return 'medium'
    elif vram >= 5: return 'small'
    elif vram >= 2: return 'base'
    else: return 'tiny'

class RealTimeLogHandler:
    def __init__(self):
        self.log_queue = queue.Queue()
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def put_log(self, message):
        self.log_queue.put(message)

    def process_logs(self):
        while not self.log_queue.empty() and self.running:
            try:
                message = self.log_queue.get_nowait()
                self._display_log(message)
            except queue.Empty:
                break
        if self.running:
            app.after(100, self.process_logs)
            
    def _display_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_text.configure(state='normal')
        log_text.insert('end', f"[{timestamp}] {message}\n")
        log_text.configure(state='disabled')
        log_text.see('end')
        app.update_idletasks()

log_handler = RealTimeLogHandler()

class OpenAIConfigWindow(ctk.CTkToplevel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title("OpenAI Configuration")
        self.geometry("500x300")
        self.resizable(False, False)
        
        self.frame = ctk.CTkFrame(self, corner_radius=12)
        self.frame.pack(padx=20, pady=20, fill="both", expand=True)
        
        ctk.CTkLabel(self.frame, text="🔑 OpenAI Configuration", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
        
        ctk.CTkLabel(self.frame, text="API Key:").pack(pady=(5, 0))
        self.api_key_entry = ctk.CTkEntry(self.frame, width=400, placeholder_text="sk-...")
        self.api_key_entry.pack(pady=5)
        if current_openai_key:
            self.api_key_entry.insert(0, current_openai_key)
        
        ctk.CTkLabel(self.frame, text="Model:").pack(pady=(10, 0))
        self.model_var = ctk.StringVar(value=current_openai_model)
        self.model_menu = ctk.CTkComboBox(self.frame, 
                                        width=400,
                                        values=["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
                                        variable=self.model_var)
        self.model_menu.pack(pady=5)
        
        btn_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        ctk.CTkButton(btn_frame, text="Save", command=self.save_config, width=120, fg_color="#4cc9f0").pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", command=self.destroy, width=120, fg_color="transparent", border_color="#4cc9f0", text_color="#4cc9f0").pack(side="right", padx=10)
    
    def save_config(self):
        api_key = self.api_key_entry.get().strip()
        model = self.model_var.get().strip()
        
        if not api_key.startswith("sk-"):
            mb.showerror("Error", "API Key must start with 'sk-'")
            return
        
        script_dir = os.path.dirname(os.path.realpath(__file__))
        env_path = os.path.join(script_dir, ".env")   
        
        try:
            with open(env_path, "w") as f:
                f.write(f"OPENAI_API_KEY={api_key}\n")
                f.write(f"OPENAI_MODEL={model}\n")
            
            mb.showinfo("Success", "Configuration saved successfully")
            self.destroy()
            update_openai_ui_state(api_key)
        except Exception as e:
            mb.showerror("Error", f"Could not save: {str(e)}")

def update_openai_ui_state(api_key=None):
    has_key = bool(api_key) if api_key is not None else bool(current_openai_key)
    btn_openai.configure(text="Configure OpenAI" if has_key else "Add API Key",
                        fg_color="#4cc9f0" if has_key else "transparent",
                        text_color="white" if has_key else "#4cc9f0",
                        border_width=1 if not has_key else 0)
    chk_openai.configure(state="normal" if has_key else "disabled")

def setup_openai():
    global openai_config_window
    if openai_config_window is None or not openai_config_window.winfo_exists():
        openai_config_window = OpenAIConfigWindow(app)
        openai_config_window.grab_set()  # Para que sea modal
        app.wait_window(openai_config_window)
    else:
        openai_config_window.lift()

class TranscriptionWorker(threading.Thread):
    def __init__(self, cmd):
        super().__init__(daemon=True)
        self.cmd = cmd

    def run(self):
        global transcription_process
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"

            transcription_process = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1,
                universal_newlines=True,
                env=env
            )

            for line in transcription_process.stdout:
                if line:
                    self.handle_log_line(line.strip())

            transcription_process.wait()

            if transcription_process.returncode == 0:
                log_handler.put_log("✅ Transcription completed")
                mb.showinfo("Success", "Process finished successfully")
            else:
                raise Exception("Transcription error")

        except Exception as e:
            log_handler.put_log(f"❌ ERROR: {str(e)}")
            mb.showerror("Error", str(e))

        finally:
            log_handler.stop()
            btn_run.configure(state='normal', text="Start transcription")

    def handle_log_line(self, line):
        log_handler.put_log(line)

        if "Transcribed" in line and "segments" in line:
            match = re.search(r"Transcribed (\d+) segments", line)
            if match:
                tracker.total_segments = int(match.group(1))

        segment_match = re.match(r"^\s*(\d+\.\d+) --> (\d+\.\d+)", line)
        if segment_match:
            tracker.processed_segments += 1
            progress.set(tracker.processed_segments / max(tracker.total_segments, 1))
            update_progress_display()

def select_file():
    file_path = fd.askopenfilename(filetypes=[("Video/Audio Files", "*.mp4 *.mkv *.mp3 *.wav *.flac *.aac *.mov *.avi")])
    if file_path:
        entry_file.delete(0, 'end')
        entry_file.insert(0, file_path)
        btn_browse.configure(text=os.path.basename(file_path)[:20] + "..." if len(os.path.basename(file_path)) > 20 else os.path.basename(file_path))
        log_handler.put_log(f"Selected file: {os.path.basename(file_path)}")

def update_progress_display():
    estimate = tracker.get_estimate()
    if tracker.total_segments > 0:
        text = f"Progress: {tracker.processed_segments}/{tracker.total_segments}"
        if estimate:
            time_label.configure(text=f"{text} | Remaining time: {estimate}")
        else:
            time_label.configure(text=text)
    else:
        time_label.configure(text="Preparing...")

def run_transcription():
    file_path = entry_file.get().strip()
    if not file_path:
        mb.showwarning("Error", "Select a file first")
        return

    btn_run.configure(state='disabled', text="Processing...")
    progress.set(0)
    tracker.start()
    log_handler.start()
    app.after(100, log_handler.process_logs)
    clear_logs()
    log_handler.put_log("Starting transcription process...")

    model = model_combobox.get()
    language = lang_combobox.get()
    translate = var_translate.get()
    use_openai = var_openai.get() and current_openai_key

    script_dir = os.path.dirname(os.path.realpath(__file__))
    autosub_path = os.path.join(script_dir, "autosub.py")

    cmd = ["python", "-u", autosub_path, file_path, "--model", model]

    if language != 'auto':
        cmd += ["-l", language]
    if translate:
        cmd += ["-t"]
    if use_openai:
        cmd += ["--openai"]
        log_handler.put_log("Using OpenAI for translation")

    worker = TranscriptionWorker(cmd)
    worker.start()

def clear_logs():
    log_text.configure(state='normal')
    log_text.delete('1.0', 'end')
    log_text.configure(state='disabled')

def on_close():
    global transcription_process
    if transcription_process and transcription_process.poll() is None:
        transcription_process.terminate()
        transcription_process.wait()
    app.destroy()

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def set_appuser_model_id():
    # Necesario para que el icono aparezca correctamente en la barra de tareas
    myappid = u'mi.aplicacion.autotranscript.1'  # Cualquier string único
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

def set_taskbar_icon(window, icon_path):
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    # Convertir el path a wchar_t* para WinAPI
    hicon = ctypes.windll.user32.LoadImageW(0, icon_path, 1, 0, 0, 0x00000010)
    if hicon:
        ctypes.windll.user32.SendMessageW(hwnd, 0x80, 1, hicon)  # ICON_BIG
        ctypes.windll.user32.SendMessageW(hwnd, 0x80, 0, hicon)  # ICON_SMALL
app = ctk.CTk()
app.title("AutoTranscript GUI")

if hasattr(sys, '_MEIPASS'):
    base_path = sys._MEIPASS
else:
    base_path = os.path.abspath(".")

icon_path = os.path.join(base_path, "icon.ico")
app.iconbitmap(icon_path)

app.iconbitmap(icon_path)
set_appuser_model_id()
set_taskbar_icon(app, icon_path)
app.geometry("700x850")
app.resizable(False, False)
app.protocol("WM_DELETE_WINDOW", on_close)

main_frame = ctk.CTkFrame(app, corner_radius=12)
main_frame.pack(padx=20, pady=20, fill="both", expand=True)

ctk.CTkLabel(main_frame, text="🔊 AutoTranscript GUI", font=ctk.CTkFont(size=24, weight="bold"), text_color="#4cc9f0").pack(pady=(20, 15))

config_frame = ctk.CTkFrame(main_frame, corner_radius=8, fg_color="transparent")
config_frame.pack(pady=(0, 10), padx=20, fill="x")

file_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
file_frame.pack(fill="x", pady=5)

ctk.CTkLabel(file_frame, text="File:", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 10))
entry_file = ctk.CTkEntry(file_frame, placeholder_text="Select a file...", width=300)
#entry_file.bind("<Key>", lambda e: "break")
entry_file.pack(side="left", fill="x", expand=True)
btn_browse = ctk.CTkButton(file_frame, text="Browse", command=select_file, width=100, fg_color="#4cc9f0", hover_color="#4895ef")
btn_browse.pack(side="right", padx=(5, 0))

settings_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
settings_frame.pack(fill="x", pady=10)

lang_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
lang_frame.pack(side="left", fill="x", expand=True, padx=5)
ctk.CTkLabel(lang_frame, text="Language:", font=ctk.CTkFont(size=14)).pack(anchor="w")
lang_combobox = ctk.CTkComboBox(lang_frame, values=whisper_languages, width=140, dropdown_fg_color="#2b2d42", button_color="#4cc9f0", state="readonly")
lang_combobox.set("auto")
lang_combobox.pack(fill="x")

model_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
model_frame.pack(side="right", fill="x", expand=True, padx=5)
ctk.CTkLabel(model_frame, text="Model:", font=ctk.CTkFont(size=14)).pack(anchor="w")
model_combobox = ctk.CTkComboBox(model_frame, values=whisper_models, width=140, dropdown_fg_color="#2b2d42", button_color="#4cc9f0", state="readonly")
model_combobox.set(suggest_model())
model_combobox.pack(fill="x")

translate_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
translate_frame.pack(fill="x", pady=10)

var_translate = ctk.BooleanVar()
chk_translate = ctk.CTkCheckBox(translate_frame, text="Translate to English", variable=var_translate, 
                               checkbox_width=18, checkbox_height=18, border_width=2, 
                               fg_color="#4cc9f0", hover_color="#4895ef")
chk_translate.pack(side="left", padx=(0, 20))

var_openai = ctk.BooleanVar()
chk_openai = ctk.CTkCheckBox(translate_frame, text="Use OpenAI (better quality)", variable=var_openai,
                            checkbox_width=18, checkbox_height=18, border_width=2,
                            fg_color="#4cc9f0", hover_color="#4895ef",
                            state="normal" if current_openai_key else "disabled")
chk_openai.pack(side="left")

btn_openai = ctk.CTkButton(translate_frame, text="Configure OpenAI" if current_openai_key else "Add API Key",
                          command=setup_openai, width=180, height=30,
                          fg_color="#4cc9f0" if current_openai_key else "transparent",
                          hover_color="#4895ef",
                          border_width=1 if not current_openai_key else 0,
                          border_color="#4cc9f0",
                          text_color="white" if current_openai_key else "#4cc9f0")
btn_openai.pack(side="right")

btn_run = ctk.CTkButton(main_frame, text="Start transcription", command=run_transcription, 
                       height=45, font=ctk.CTkFont(size=14, weight="bold"), 
                       fg_color="#4cc9f0", hover_color="#4895ef")
btn_run.pack(pady=10, padx=40, fill="x")

progress = ctk.DoubleVar()
progress_bar = ctk.CTkProgressBar(main_frame, variable=progress, height=20, corner_radius=8, progress_color="#4cc9f0")
progress_bar.pack(pady=10, padx=20, fill="x")

time_label = ctk.CTkLabel(main_frame, text="", font=ctk.CTkFont(size=14))
time_label.pack(pady=(0, 10))

log_frame = ctk.CTkFrame(main_frame, corner_radius=8)
log_frame.pack(padx=20, pady=(10, 20), fill="both", expand=True)

log_text = ctk.CTkTextbox(log_frame, state='disabled', font=("Consolas", 12), wrap="word")
log_text.pack(padx=10, pady=10, fill="both", expand=True)

update_openai_ui_state()

app.mainloop()