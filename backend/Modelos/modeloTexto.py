from transformers import BlipProcessor, BlipForConditionalGeneration
from PIL import Image
import torch
import cv2
import os
import glob
import whisper

# ----------- IMAGEN A TEXTO -----------
def imagen_a_texto(img_paths):
    processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
    model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
    captions = []
    for img_path in img_paths:
        image = Image.open(img_path).convert("RGB")
        print(f"Imagen {img_path} Cargada Correctamente")
        inputs = processor(image, return_tensors="pt")
        out = model.generate(**inputs)
        caption = processor.decode(out[0], skip_special_tokens=True)
        print(f"Descripción imagen generada: {caption}")
        captions.append(caption)
    return captions

# ----------- VIDEO A TEXTO -----------
def video_a_texto(video_path, frames_folder="frames", frame_rate=60, max_caption_length=50, num_beams=1, temperature=0.8):
    os.makedirs(frames_folder, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    count = 0
    saved = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if count % frame_rate == 0:
            frame_path = os.path.join(frames_folder, f"frame_{saved}.jpg")
            cv2.imwrite(frame_path, frame)
            saved += 1
        count += 1
    cap.release()
    print(f"{saved} frames extraídos")
    processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
    model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    descriptions = []
    for frame_path in sorted(glob.glob(os.path.join(frames_folder, "*.jpg"))):
        image = Image.open(frame_path).convert("RGB")
        inputs = processor(image, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        out = model.generate(
            **inputs,
            max_length=max_caption_length,
            num_beams=num_beams,
            do_sample=False
        )
        caption = processor.decode(out[0], skip_special_tokens=True)
        descriptions.append(caption)
    full_text = " ".join(descriptions)
    print("\nResumen completo del video:")
    print(full_text)
    return full_text

# ----------- AUDIO A TEXTO -----------
def audio_a_texto(audio_path, model_size="large"):
    model = whisper.load_model(model_size)
    print("Transcribiendo audio...")
    result = model.transcribe(audio_path)
    print("\nTexto detectado:\n")
    print(result["text"])
    return result["text"]
