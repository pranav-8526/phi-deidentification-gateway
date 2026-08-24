import io
import re
import json
import time
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import pypdf
from src.gateway import DeIDGateway

app = FastAPI(title="PHI De-identification Gateway", version="1.0.0")
gateway = DeIDGateway()

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
SAMPLES_FILE = BASE_DIR / "data" / "samples" / "synthetic_clinical_notes.json"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _clean_pdf_text(text: str) -> str:
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
    return text.strip()


class DeidentifyReq(BaseModel):
    text: str
    patient_seed: Optional[int] = None

class RehydrateReq(BaseModel):
    llm_response: str
    encrypted_mapping: str

class RoundtripReq(BaseModel):
    text: str


@app.get("/")
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        resp = FileResponse(index_file)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp
    return {"status": "ok"}

@app.get("/health")
def health():
    return {"status": "HEALTHY"}

@app.get("/samples")
def get_samples():
    if SAMPLES_FILE.exists():
        try:
            with open(SAMPLES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return []

@app.post("/deidentify")
def deidentify(req: DeidentifyReq):
    try:
        t0 = time.perf_counter()
        masked, mapping = gateway.deidentify(req.text, req.patient_seed)
        elapsed = (time.perf_counter() - t0) * 1000
        return {
            "masked_text": masked,
            "encrypted_mapping": mapping,
            "latency": {"deidentification_ms": round(elapsed, 2), "total_ms": round(elapsed, 2)},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        t0 = time.perf_counter()
        content = await file.read()
        filename_lower = file.filename.lower()

        if filename_lower.endswith(".pdf"):
            reader = pypdf.PdfReader(io.BytesIO(content))
            pages = [_clean_pdf_text(p.extract_text()) for p in reader.pages
                     if p.extract_text() and p.extract_text().strip()]
            text = "\n\n".join(pages) if pages else (
                "⚠️ [WARNING: SCANNED PDF DETECTED]\n"
                "No embedded text found. Please run OCR before de-identification."
            )
        else:
            text = content.decode("utf-8", errors="ignore")

        t1 = time.perf_counter()
        masked, mapping = gateway.deidentify(text)
        t2 = time.perf_counter()

        return {
            "filename": file.filename,
            "raw_text": text,
            "masked_text": masked,
            "encrypted_mapping": mapping,
            "latency": {
                "pdf_extraction_ms": round((t1 - t0) * 1000, 2),
                "deidentification_ms": round((t2 - t1) * 1000, 2),
                "total_ms": round((t2 - t0) * 1000, 2),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/rehydrate")
def rehydrate(req: RehydrateReq):
    try:
        t0 = time.perf_counter()
        restored = gateway.rehydrate(req.llm_response, req.encrypted_mapping)
        elapsed = (time.perf_counter() - t0) * 1000
        return {
            "restored_text": restored,
            "latency": {"rehydration_ms": round(elapsed, 2), "total_ms": round(elapsed, 2)},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/roundtrip")
def roundtrip(req: RoundtripReq):
    try:
        t0 = time.perf_counter()
        masked, mapping = gateway.deidentify(req.text)
        simulated_llm = f"Clinical Note Summary:\nPatient note evaluated.\nMasked output: {masked}"
        rehydrated = gateway.rehydrate(simulated_llm, mapping)
        elapsed = (time.perf_counter() - t0) * 1000
        return {
            "raw_input": req.text,
            "masked_text": masked,
            "simulated_llm_response": simulated_llm,
            "final_rehydrated_text": rehydrated,
            "latency": {"roundtrip_ms": round(elapsed, 2), "total_ms": round(elapsed, 2)},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
