import os
import urllib.request
import numpy as np
from faster_whisper import WhisperModel
from piper.voice import PiperVoice
import wave
import io

import sys

# STT Model initialization
print("Loading Whisper STT model (base.en) for instant loading and good noise handling...")
whisper_model = WhisperModel("base.en", device="cpu", compute_type="int8")
print("Whisper model loaded.")

# TTS Model initialization
PIPER_MODEL_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/low/en_US-lessac-low.onnx"
PIPER_CONFIG_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/low/en_US-lessac-low.onnx.json"
MODEL_PATH = "en_US-lessac-low.onnx"
CONFIG_PATH = "en_US-lessac-low.onnx.json"

def show_progress(block_num, block_size, total_size):
    downloaded = block_num * block_size
    if total_size > 0:
        percent = downloaded * 100 / total_size
        sys.stdout.write(f"\rDownloading: {percent:.1f}%")
        sys.stdout.flush()

if not os.path.exists(MODEL_PATH):
    print("Downloading Piper TTS model (low quality, faster)...")
    urllib.request.urlretrieve(PIPER_MODEL_URL, MODEL_PATH, reporthook=show_progress)
    print() # New line after progress
if not os.path.exists(CONFIG_PATH):
    urllib.request.urlretrieve(PIPER_CONFIG_URL, CONFIG_PATH)

print("Loading Piper TTS voice...")
piper_voice = PiperVoice.load(MODEL_PATH, config_path=CONFIG_PATH)
print("Piper voice loaded.")

def transcribe_audio(pcm_data: bytes) -> str:
    """Transcribe raw 16kHz Int16 PCM audio data to text."""
    # Convert PCM bytes to float32 numpy array normalized between -1.0 and 1.0
    audio_np = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
    
    max_amp = float(np.max(np.abs(audio_np))) if len(audio_np) > 0 else 0.0
    print(f"[DEBUG] STT received {len(audio_np)} samples, max amplitude: {max_amp:.4f}")
    
    if max_amp < 0.01:
        print("[DEBUG] Audio appears to be practically silent.")
        return ""
        
    segments, info = whisper_model.transcribe(audio_np, beam_size=5, language="en")
    
    text = " ".join([segment.text for segment in segments])
    return text.strip()

def synthesize_audio(text: str) -> bytes:
    """Synthesize text to a WAV audio file buffer (16kHz, mono, int16)."""
    audio_stream = piper_voice.synthesize(text)
    
    out_buffer = io.BytesIO()
    with wave.open(out_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2) # 2 bytes for int16
        wav_file.setframerate(16000)
        for chunk in audio_stream:
            wav_file.writeframes(chunk.audio_int16_bytes)
            
    return out_buffer.getvalue()
