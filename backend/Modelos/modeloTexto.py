import io
import os
import tempfile
import traceback

# Asegurar que ffmpeg (instalado via winget) esté en el PATH
_FFMPEG_BIN = r"C:\Users\CEP-TARDA\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
if _FFMPEG_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _FFMPEG_BIN + os.pathsep + os.environ.get("PATH", "")

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Modelo Texto")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------- IMAGEN A TEXTO -----------
@app.post("/imagen-a-texto")
async def imagen_a_texto(imagen: UploadFile = File(...)):
    try:
        from PIL import Image
        from transformers import BlipProcessor, BlipForConditionalGeneration
        file_bytes = await imagen.read()
        image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
        inputs = processor(image, return_tensors="pt")
        out = model.generate(**inputs)
        caption = processor.decode(out[0], skip_special_tokens=True)
        print(f"Caption generado: {caption}")
        return {"caption": caption}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ----------- VIDEO A TEXTO -----------
@app.post("/video-a-texto")
async def video_a_texto(video: UploadFile = File(...)):
    file_bytes = await video.read()
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(file_bytes)
        del file_bytes
        import cv2
        from PIL import Image
        from transformers import BlipProcessor, BlipForConditionalGeneration
        cap = cv2.VideoCapture(tmp_path)
        frames = []
        count = 0
        frame_rate = 60
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            if count % frame_rate == 0:
                frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            count += 1
        cap.release()
        if not frames:
            raise HTTPException(status_code=400, detail="No se pudieron extraer frames del video")
        processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
        descriptions = []
        for frame_array in frames:
            image = Image.fromarray(frame_array)
            inputs = processor(image, return_tensors="pt")
            out = model.generate(**inputs, max_length=50, num_beams=1)
            caption = processor.decode(out[0], skip_special_tokens=True)
            descriptions.append(caption)
        texto = " ".join(descriptions)
        print(f"Video texto generado: {texto}")
        return {"texto": texto}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

# ----------- AUDIO A TEXTO -----------
@app.post("/audio-a-texto")
async def audio_a_texto(audio: UploadFile = File(...)):
    file_bytes = await audio.read()
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(file_bytes)
        del file_bytes
        import whisper
        whisper_model = whisper.load_model("base")
        result = whisper_model.transcribe(tmp_path)
        print(f"Texto detectado: {result['text']}")
        return {"texto": result["text"]}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
