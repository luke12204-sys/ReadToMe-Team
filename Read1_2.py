"""
Revision: 1.2.0
Changelog:
- Migrated from pyttsx3 to gTTS (Google Text-to-Speech).
- Integrated 'pygame.mixer' to handle audio playback (Play/Pause/Stop).
- Updated dependency check to include gtts and pygame.
- Added temporary file handling for generated speech assets.
"""

import sys
import os
import threading
import tempfile
import tkinter as tk
from tkinter import filedialog, ttk, messagebox

# --- Pre-flight Dependency Check ---
def install_dependencies():
    """Ensures gtts, pygame, and PyPDF2 are available."""
    try:
        import gtts
        import pygame
        import PyPDF2
    except ImportError as e:
        missing = str(e).split("'")[-2]
        print(f"[!] Critical Error: Module '{missing}' not found.")
        print(f"FIX: Run this command in your terminal:\n")
        print(f"{sys.executable} -m pip install gtts pygame PyPDF2\n")
        sys.exit(1)

install_dependencies()

from gtts import gTTS
import pygame
import PyPDF2

class ReadingPrysmApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Reading PrYsm")
        self.root.geometry("500x700")
        self.root.configure(bg="#ffffff")

        # Initialize Pygame Mixer for audio control
        pygame.mixer.init()
        
        self.pdf_text = ""
        self.temp_audio_file = None
        self.is_paused = False
        self.is_loaded = False

        self._setup_ui()

    def _setup_ui(self):
        """Graphical interface setup based on user sketch."""
        
        # Header Section
        header_frame = tk.Frame(self.root, bg="#ffffff")
        header_frame.pack(pady=20)
        tk.Label(header_frame, text="Reading ", font=("Helvetica", 24, "bold"), bg="#ffffff").pack(side=tk.LEFT)
        
        colors = ["#ff4d4d", "#ffaf40", "#fffa65", "#32ff7e", "#7efff5", "#18dcff", "#7d5fff"]
        for i, char in enumerate("PrYsm"):
            tk.Label(header_frame, text=char, font=("Helvetica", 24, "bold"), 
                     fg=colors[i], bg="#ffffff").pack(side=tk.LEFT)

        # Primary Action: Play/Pause (The Red Triangle from sketch)
        self.play_btn = tk.Button(self.root, text="▶", font=("Helvetica", 40), 
                                  fg="red", bg="white", borderwidth=0, 
                                  command=self.handle_play_pause)
        self.play_btn.pack(pady=10)

        # File & Stop Controls
        ctrl_frame = tk.Frame(self.root, bg="#ffffff")
        ctrl_frame.pack(pady=10)
        
        ttk.Button(ctrl_frame, text="Load PDF", command=self.load_pdf).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame, text="Stop", command=self.stop_audio).pack(side=tk.LEFT, padx=5)

        # Volume Slider (Simulated in pygame)
        tk.Label(self.root, text="Volume", bg="#ffffff").pack()
        self.volume_slider = ttk.Scale(self.root, from_=0.0, to=1.0, orient=tk.HORIZONTAL, 
                                       length=200, command=self.update_volume)
        self.volume_slider.set(0.7)
        self.volume_slider.pack(pady=10)

        # Feature Grid Placeholder
        self.grid_frame = tk.Frame(self.root, bd=1, relief=tk.SOLID, bg="#fcfcfc")
        self.grid_frame.pack(padx=30, pady=20, fill=tk.BOTH, expand=True)
        for r in range(3):
            for c in range(4):
                tk.Frame(self.grid_frame, bd=1, relief=tk.SUNKEN, width=80, height=40).grid(row=r, column=c, padx=2, pady=2)
        
        self.status_label = tk.Label(self.root, text="Ready", bg="#ffffff", fg="gray")
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

    def load_pdf(self):
        """Loads PDF, extracts text, and prepares gTTS audio."""
        file_path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if not file_path:
            return

        self.status_label.config(text="Extracting text...")
        self.root.update_idletasks()

        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = "".join([page.extract_text() for page in reader.pages])
                self.pdf_text = text.strip()

            if not self.pdf_text:
                messagebox.showwarning("Empty PDF", "No readable text found in this file.")
                return

            self.status_label.config(text="Converting to speech (via Google)...")
            self.root.update_idletasks()
            
            # Generate speech on a background thread to prevent UI freezing
            threading.Thread(target=self._generate_audio, daemon=True).start()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load file: {e}")

    def _generate_audio(self):
        """Worker for gTTS conversion."""
        try:
            tts = gTTS(text=self.pdf_text, lang='en')
            
            # Create a named temp file that persists until we manually delete it
            temp_dir = tempfile.gettempdir()
            self.temp_audio_file = os.path.join(temp_dir, "prysm_temp_audio.mp3")
            tts.save(self.temp_audio_file)
            
            self.is_loaded = True
            self.status_label.config(text="Speech ready to play.")
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("API Error", f"gTTS failed: {e}"))

    def handle_play_pause(self):
        """Toggles between Play, Pause, and Resume."""
        if not self.is_loaded:
            messagebox.showinfo("Wait", "Please load a PDF and wait for conversion.")
            return

        if not pygame.mixer.music.get_busy() and not self.is_paused:
            # Start fresh playback
            pygame.mixer.music.load(self.temp_audio_file)
            pygame.mixer.music.play()
            self.play_btn.config(text="⏸", fg="orange")
            self.status_label.config(text="Reading...")
        elif self.is_paused:
            # Resume
            pygame.mixer.music.unpause()
            self.is_paused = False
            self.play_btn.config(text="⏸", fg="orange")
            self.status_label.config(text="Reading...")
        else:
            # Pause
            pygame.mixer.music.pause()
            self.is_paused = True
            self.play_btn.config(text="▶", fg="green")
            self.status_label.config(text="Paused")

    def stop_audio(self):
        """Stops playback and resets state."""
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        self.is_paused = False
        self.play_btn.config(text="▶", fg="red")
        self.status_label.config(text="Stopped")

    def update_volume(self, val):
        """Real-time volume control."""
        pygame.mixer.music.set_volume(float(val))

if __name__ == "__main__":
    root = tk.Tk()
    app = ReadingPrysmApp(root)
    
    # Cleanup temp file on close
    def on_closing():
        pygame.mixer.quit()
        if app.temp_audio_file and os.path.exists(app.temp_audio_file):
            try:
                os.remove(app.temp_audio_file)
            except:
                pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()