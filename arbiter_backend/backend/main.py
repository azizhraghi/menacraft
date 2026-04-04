"""
ARBITER — AI Forensic Claims Intelligence Platform
FastAPI Backend — Main Application
"""

import os
import io
import uuid
import base64
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

from agents.forensics import run_ela, run_fft, check_duplicate, store_phash
from agents.semantic import run_clip_consistency, run_mahalanobis, run_sam_severity
from agents.temporal import run_temporal_analysis
from agents.debate import run_prosecutor, run_defender, run_typology
from agents.verdict import compute_verdict
from report.generator import generate_report

CLAIMS_STORE = {}

app = FastAPI(title="ARBITER API", description="AI Forensic Claims Intelligence Platform", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "operational", "system": "ARBITER", "version": "1.0.0"}


@app.post("/analyze")
async def analyze_claim(
    image: UploadFile = File(...),
    claim_text: str = Form(default=""),
    incident_type: str = Form(default="collision"),
    claim_date: str = Form(default=""),
    claim_location: str = Form(default=""),
):
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    claim_id = f"ARB-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    try:
        raw_bytes = await image.read()
        pil_image = Image.open(io.BytesIO(raw_bytes))

        if pil_image.mode not in ("RGB", "L"):
            pil_image = pil_image.convert("RGB")

        orig_buf = io.BytesIO()
        pil_image.copy().resize((400, 300), Image.LANCZOS).save(orig_buf, format="JPEG", quality=85)
        image_b64 = base64.b64encode(orig_buf.getvalue()).decode()

        ela_result = run_ela(pil_image)
        fft_result = run_fft(pil_image)
        phash_result = check_duplicate(pil_image, claim_id)
        store_phash(claim_id, pil_image)

        clip_result = run_clip_consistency(pil_image, claim_text)
        mahal_result = run_mahalanobis(pil_image, incident_type)
        sam_result = run_sam_severity(pil_image)

        temporal_result = run_temporal_analysis(
            pil_image,
            claim_date=claim_date if claim_date else None,
            claim_location=claim_location if claim_location else None
        )

        layer_scores = {
            "ela": ela_result,
            "fft": fft_result,
            "phash": phash_result,
            "clip": clip_result,
            "mahalanobis": mahal_result,
            "sam": sam_result,
            "temporal": temporal_result,
        }

        prosecutor_result = run_prosecutor(layer_scores, claim_text)
        defender_result = run_defender(layer_scores, claim_text)
        typology_result = run_typology(layer_scores, claim_text)

        debate = {
            "prosecutor": prosecutor_result,
            "defender": defender_result,
            "typology": typology_result,
        }

        verdict = compute_verdict(layer_scores, typology_result, sam_result)

        full_result = {
            "claim_id": claim_id,
            "timestamp": datetime.now().isoformat(),
            "incident_type": incident_type,
            "claim_text": claim_text,
            "layer_scores": layer_scores,
            "debate": debate,
            "verdict": verdict,
            "image_b64": image_b64,
        }

        CLAIMS_STORE[claim_id] = full_result
        return JSONResponse(content=_serialize_result(full_result))

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.get("/report/{claim_id}")
async def download_report(claim_id: str):
    if claim_id not in CLAIMS_STORE:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    result = CLAIMS_STORE[claim_id]
    try:
        pdf_bytes = generate_report(claim_id, result, result.get("image_b64"))
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="ARBITER_{claim_id}.pdf"'}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")


@app.get("/claim/{claim_id}")
async def get_claim(claim_id: str):
    if claim_id not in CLAIMS_STORE:
        raise HTTPException(status_code=404, detail="Claim not found")
    return JSONResponse(content=_serialize_result(CLAIMS_STORE[claim_id]))


@app.get("/claims")
async def list_claims():
    summary = []
    for cid, data in CLAIMS_STORE.items():
        verdict = data.get("verdict", {})
        summary.append({
            "claim_id": cid,
            "timestamp": data.get("timestamp"),
            "action": verdict.get("action"),
            "risk_score": verdict.get("risk_score"),
            "fraud_type": verdict.get("fraud_type"),
        })
    return {"claims": sorted(summary, key=lambda x: x["timestamp"], reverse=True)}


def _serialize_result(result: dict) -> dict:
    import numpy as np

    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean(v) for v in obj]
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, float) and (obj != obj):
            return None
        return obj

    return clean(result)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
