"""
Revision: 1.6.0
Changelog:
- Added comprehensive developer-level comments across all major modules.
- Clarified threading logic, audio synchronization, and text sanitization protocols.
- Logic remains 100% consistent with v1.5.0.
"""

import sys
import os
import threading
import tempfile
import time
import re
import tkinter as tk
from tkinter import filedialog, messagebox

# --- Dependency Management ---
# We verify dependencies at runtime to provide actionable error messages 
# rather than letting the script crash with a cryptic ModuleNotFoundError.
def install_dependencies():
    try:
        import customtkinter # Modern UI wrapper
        import gtts          # Google TTS API client
        import pygame        # Audio mixer backend
        import PyPDF2        # PDF parsing engine
        import mutagen       # Audio metadata (duration) extractor
    except ImportError as e:
        missing = str(e).split("'")[-2]
        print(f"[!] Critical Error: Module '{missing}' not found.")
        print(f"FIX: Run: {sys.executable} -m pip install customtkinter gtts pygame PyPDF2 mutagen\n")
        sys.exit(1)

install_dependencies()

import customtkinter as ctk
from gtts import gTTS
import pygame
import PyPDF2
from mutagen.mp3 import MP3

# Global UI Configuration
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class ReadingPrysmApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Reading PrYsm")
        self.root.geometry("600x850")

        # --- Audio Engine Initialization ---
        # gTTS generates MP3s at 24000Hz. If we don't match this frequency 
        # in the pre_init, pygame might default to 44.1kHz, causing silence.
        try:
            pygame.mixer.pre_init(24000, -16, 2, 2048)
            pygame.mixer.init()
        except Exception as e:
            print(f"Mixer Init Warning: {e}")

        # --- Reactive State Variables ---
        self.pdf_text = ""
        self.temp_audio_file = None
        self.is_paused = False
        self.is_loaded = False
        self.duration_seconds = 0
        self.current_seek_point = 0 # Tracks manual 'jumps' in playback time
        self.is_seeking = False     # Flag to stop the UI from jumping while the user drags the slider

        self._setup_modern_ui()
        self._start_update_loop() # Start the UI heart-beat

    def _setup_modern_ui(self):
        """Initializes the CustomTkinter widget tree."""
        
        # 1. Header Section: Branding and Light/Dark Switch
        header_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        header_frame.pack(pady=(30, 10), padx=20, fill="x")

        title_colors_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_colors_frame.pack(side="left")
        ctk.CTkLabel(title_colors_frame, text="Reading ", font=("Helvetica", 32, "bold")).pack(side="left")
        
        # Color-cycling for 'PrYsm' branding
        colors = ["#ff5252", "#ffb142", "#fffa65", "#32ff7e", "#7efff5", "#18dcff", "#7d5fff"]
        for i, char in enumerate("PrYsm"):
            ctk.CTkLabel(title_colors_frame, text=char, font=("Helvetica", 32, "bold"), text_color=colors[i]).pack(side="left")

        self.theme_switch = ctk.CTkSwitch(header_frame, text="Dark Mode", command=self.toggle_theme_mode)
        if ctk.get_appearance_mode() == "Dark": self.theme_switch.select()
        self.theme_switch.pack(side="right")

        # 2. Information Display: Shows currently selected filename
        self.file_info_frame = ctk.CTkFrame(self.root, border_width=2, corner_radius=15, fg_color=("#f2f2f2", "#1a1a1a"))
        self.file_info_frame.pack(padx=30, pady=10, fill="x")
        
        ctk.CTkLabel(self.file_info_frame, text="SELECTED FILE", font=("Helvetica", 10, "bold"), text_color="gray").pack(pady=(10, 0))
        self.file_name_label = ctk.CTkLabel(self.file_info_frame, text="No File Loaded", font=("Helvetica", 14, "italic"))
        self.file_name_label.pack(pady=(0, 10), padx=20)

        # 3. Primary Controls: Centralized Play/Pause logic
        self.play_btn = ctk.CTkButton(self.root, text="▶", font=("Helvetica", 60), fg_color="#ff5252",
                                     hover_color="#ff793f", height=120, width=120, corner_radius=60,
                                     command=self.handle_play_pause)
        self.play_btn.pack(pady=20)

        # 4. Secondary Action Buttons
        action_btns_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        action_btns_frame.pack(pady=10)
        ctk.CTkButton(action_btns_frame, text="Load PDF", command=self.load_pdf).pack(side="left", padx=10)
        ctk.CTkButton(action_btns_frame, text="Stop", fg_color="gray", command=self.stop_audio).pack(side="left", padx=10)

        # 5. Seek/Progress Bar: Allows user to scroll through audio
        progress_container = ctk.CTkFrame(self.root, fg_color="transparent")
        progress_container.pack(fill="x", padx=40, pady=(20, 0))

        self.time_current_label = ctk.CTkLabel(progress_container, text="00:00", font=("Courier", 12))
        self.time_current_label.pack(side="left")

        self.seek_slider = ctk.CTkSlider(progress_container, from_=0, to=100, command=self.seek_audio)
        self.seek_slider.set(0)
        self.seek_slider.pack(side="left", fill="x", expand=True, padx=10)
        
        # We bind mouse events to 'is_seeking' so the UI update loop doesn't 
        # fight with the user's mouse while they are dragging.
        self.seek_slider.bind("<Button-1>", lambda e: self._set_seeking(True))
        self.seek_slider.bind("<ButtonRelease-1>", lambda e: self._set_seeking(False))

        self.time_total_label = ctk.CTkLabel(progress_container, text="00:00", font=("Courier", 12))
        self.time_total_label.pack(side="right")

        # 6. Volume Control
        volume_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        volume_frame.pack(pady=20, padx=80, fill="x")
        self.volume_slider = ctk.CTkSlider(volume_frame, from_=0.0, to=1.0, command=self.update_volume, height=15)
        self.volume_slider.set(0.7)
        self.volume_slider.pack(fill="x")
        
        # 7. Status Footer: Includes the RGB LED indicator
        status_footer = ctk.CTkFrame(self.root, fg_color="transparent")
        status_footer.pack(side="bottom", pady=15)

        self.status_led = ctk.CTkLabel(status_footer, text="●", font=("Helvetica", 24), text_color="#ff5252")
        self.status_led.pack(side="left", padx=5)

        self.status_label = ctk.CTkLabel(status_footer, text="System Offline", font=("Helvetica", 12), text_color="gray")
        self.status_label.pack(side="left", padx=5)

    # --- Utility Methods ---

    def update_status(self, text, state="red"):
        """Maps system state to the UI LED and label."""
        colors = {"red": "#ff5252", "yellow": "#ffb142", "green": "#32ff7e"}
        self.status_led.configure(text_color=colors.get(state, "gray"))
        self.status_label.configure(text=text)

    def sanitize_text(self, text):
        """
        Cleans text for API ingestion. gTTS often fails on:
        - PDF Ligatures (e.g., 'fi', 'fl' as single bytes)
        - Control characters (\x00-\x1F)
        - Excessive whitespace
        """
        text = text.replace('\ufb01', 'fi').replace('\ufb02', 'fl')
        text = re.sub(r'[^\x20-\x7E]+', ' ', text) # Regex: Remove non-ASCII/non-printable
        text = ' '.join(text.split())             # Normalize spaces
        return text

    def load_pdf(self):
        """Extracts and prepares PDF text for TTS conversion."""
        file_path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if not file_path: return

        self.is_loaded = False
        self.file_name_label.configure(text=os.path.basename(file_path), text_color=("#1a1a1a", "#ffffff"))
        self.update_status("Sanitizing text...", "yellow")
        
        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                # Concatenate all extracted text from every page
                raw_text = " ".join([p.extract_text() for p in reader.pages if p.extract_text()])
                self.pdf_text = self.sanitize_text(raw_text)
                
                # Stability Check: 10k characters is a safe limit for free-tier gTTS API usage
                if len(self.pdf_text) > 10000:
                    self.pdf_text = self.pdf_text[:10000]

            if not self.pdf_text:
                self.update_status("Error: No text found", "red")
                return

            self.update_status("Converting to speech...", "yellow")
            # We must use a separate thread here so the UI doesn't freeze while 
            # the gTTS library is waiting for a response from Google servers.
            threading.Thread(target=self._generate_audio, daemon=True).start()
        except Exception as e:
            self.update_status("Loading failed", "red")
            messagebox.showerror("Error", str(e))

    def _generate_audio(self):
        """Worker thread for gTTS file generation and metadata extraction."""
        try:
            tts = gTTS(text=self.pdf_text, lang='en')
            # Generate a timestamped temp file to prevent 'file in use' locks on Windows
            temp_path = os.path.join(tempfile.gettempdir(), f"prysm_{int(time.time())}.mp3")
            tts.save(temp_path)
            
            # Use Mutagen to parse MP3 headers for the precise track length
            audio = MP3(temp_path)
            self.duration_seconds = audio.info.length
            self.temp_audio_file = temp_path
            
            self.is_loaded = True
            # Safely schedule the UI update back on the main thread
            self.root.after(0, self._on_audio_ready)
        except Exception as e:
            self.root.after(0, lambda: self.update_status("API Error", "red"))
            self.root.after(0, lambda: messagebox.showerror("API Error", "Google connection failed."))

    def _on_audio_ready(self):
        """Callback to update labels once audio is fully generated and saved."""
        self.time_total_label.configure(text=self.format_time(self.duration_seconds))
        self.update_status("Speech Ready", "green")

    # --- Playback Engine ---

    def handle_play_pause(self):
        """Main state machine for Play/Pause/Resume functionality."""
        if not self.is_loaded: return
        
        if not pygame.mixer.music.get_busy() and not self.is_paused:
            # First time play or start after stop
            pygame.mixer.music.load(self.temp_audio_file)
            pygame.mixer.music.play(start=self.current_seek_point)
            self.play_btn.configure(text="⏸", fg_color="#ffb142")
            self.update_status("Reading...", "green")
        elif self.is_paused:
            # Resume existing stream
            pygame.mixer.music.unpause()
            self.is_paused = False
            self.play_btn.configure(text="⏸", fg_color="#ffb142")
            self.update_status("Reading...", "green")
        else:
            # Halt current stream
            pygame.mixer.music.pause()
            self.is_paused = True
            self.play_btn.configure(text="▶", fg_color="#32ff7e")
            self.update_status("Paused", "yellow")

    def stop_audio(self):
        """Completely halts playback and resets seeking state."""
        pygame.mixer.music.stop()
        self.is_paused = False
        self.current_seek_point = 0
        self.seek_slider.set(0)
        self.time_current_label.configure(text="00:00")
        self.play_btn.configure(text="▶", fg_color="#ff5252")
        self.update_status("Stopped", "red")

    def seek_audio(self, value):
        """Jumps to a percentage of the file based on the slider value."""
        if not self.is_loaded: return
        # Calculate offset in seconds
        new_time = (float(value) / 100) * self.duration_seconds
        self.current_seek_point = new_time
        # In pygame, play(start=x) restarts the music at the specific timestamp
        pygame.mixer.music.play(start=new_time)
        if self.is_paused: pygame.mixer.music.pause()
        self.time_current_label.configure(text=self.format_time(new_time))

    def _set_seeking(self, value):
        """Helper to manage the 'seeking' flag to prevent UI jitter."""
        self.is_seeking = value

    def format_time(self, seconds):
        """Helper to convert float seconds into MM:SS display."""
        mins, secs = divmod(int(seconds), 60)
        return f"{mins:02d}:{secs:02d}"

    def _start_update_loop(self):
        """
        The 'UI Heartbeat'. Recursively calls itself to keep the 
        Progress Slider synced with the actual audio playback position.
        """
        if pygame.mixer.music.get_busy() and not self.is_paused and not self.is_seeking:
            # get_pos() returns milliseconds since the music started playing
            current_ms = pygame.mixer.music.get_pos()
            if current_ms != -1:
                total_played_secs = (current_ms / 1000.0) + self.current_seek_point
                self.seek_slider.set((total_played_secs / self.duration_seconds) * 100)
                self.time_current_label.configure(text=self.format_time(total_played_secs))
        
        # Schedule the next heartbeat in 500ms
        self.root.after(500, self._start_update_loop)

    def toggle_theme_mode(self):
        """Switches CTK global styling between Light and Dark."""
        ctk.set_appearance_mode("Dark" if self.theme_switch.get() else "Light")

    def update_volume(self, val):
        """Real-time volume control (0.0 to 1.0)."""
        pygame.mixer.music.set_volume(float(val))

if __name__ == "__main__":
    # Entry Point
    root = ctk.CTk()
    app = ReadingPrysmApp(root)
    root.mainloop()