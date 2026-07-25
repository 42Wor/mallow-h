import io
import wave
from piper.voice import PiperVoice
voice = PiperVoice.load("en_US-lessac-low.onnx", "en_US-lessac-low.onnx.json")

out = io.BytesIO()
with wave.open(out, "wb") as wav_file:
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(16000)
    voice.synthesize("hello world", wav_file)
print(len(out.getvalue()))
