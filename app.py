from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
import json
import os

from audio_processing import transcribe_audio, synthesize_audio
from agent import Agent

app = FastAPI()

# Make sure templates directory exists
os.makedirs("templates", exist_ok=True)
templates = Jinja2Templates(directory="templates")

# Remove global main_agent
# We will instantiate it per connection

@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    audio_buffer = bytearray()
    
    async def send_log(message: str):
        try:
            await websocket.send_text(json.dumps({"type": "tool_log", "message": message}))
        except:
            pass
            
    agent = Agent(log_callback=send_log)
    
    try:
        while True:
            message = await websocket.receive()
            
            if message["type"] == "websocket.disconnect":
                print("WebSocket disconnected cleanly.")
                break
            
            if message.get("bytes"):
                # Append audio chunk to buffer
                audio_buffer.extend(message["bytes"])
            elif message.get("text"):
                data = json.loads(message["text"])
                if data.get("action") == "process":
                    if len(audio_buffer) == 0:
                        await websocket.send_text(json.dumps({"type": "log", "message": "No audio received."}))
                        continue
                        
                    # Calculate duration in seconds (16000 samples/sec, 2 bytes/sample)
                    duration = len(audio_buffer) / 32000
                    await websocket.send_text(json.dumps({"type": "log", "message": f"Processing {duration:.2f}s of audio."}))
                    
                    # Process audio
                    await websocket.send_text(json.dumps({"type": "status", "message": "Transcribing..."}))
                    text = transcribe_audio(bytes(audio_buffer))
                    audio_buffer.clear() # clear buffer for next turn
                    
                    await websocket.send_text(json.dumps({"type": "transcript", "role": "user", "text": text}))
                    
                    if not text:
                        await websocket.send_text(json.dumps({"type": "log", "message": "Could not understand audio."}))
                        continue
                        
                    # Send to Agent
                    await websocket.send_text(json.dumps({"type": "status", "message": "Agent processing..."}))
                    
                    full_response = ""
                    async for sentence in agent.chat_stream(text):
                        full_response += sentence + " "
                        await websocket.send_text(json.dumps({"type": "transcript", "role": "assistant", "text": full_response.strip()}))
                        
                        # Synthesize and stream audio chunk immediately
                        audio_bytes = synthesize_audio(sentence)
                        await websocket.send_bytes(audio_bytes)
                        
                    await websocket.send_text(json.dumps({"type": "status", "message": "Idle"}))
                    
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Error in websocket: {e}")
        try:
            await websocket.send_text(json.dumps({"type": "log", "message": f"Error: {str(e)}"}))
        except:
            pass

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
