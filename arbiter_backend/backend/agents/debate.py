"""
ARBITER LLM Debate Agent
"""

from mistralai import Mistral
import json
import os

client = Mistral(api_key=os.environ.get("MISTRAL_API_KEY", ""))

FRAUD_TYPES = {
    "GEN_AI": "Fully AI-generated damage image (no real vehicle photographed)",
    "SPLICE_FRAUD": "Real vehicle with digitally inserted or exaggerated damage",
    "RECYCLED_CLAIM": "Previously submitted image reused for a new claim",
    "PRE_EXISTING": "Pre-existing damage presented as new incident damage",
    "GEO_MISMATCH": "Location or timestamp inconsistent with claimed incident",
    "PHYSICS_FRAUD": "Damage pattern physically impossible for claimed incident type",
    "METADATA_STRIPPED": "Metadata removed to hide manipulation or image origin",
    "AUTHENTIC": "No significant fraud indicators detected"
}


def run_prosecutor(scores: dict, claim_text: str = "", image_description: str = "") -> dict:
    evidence_summary = _build_evidence_summary(scores)
    system_prompt = """You are the Prosecutor in ARBITER's AI Forensic Tribunal.
Build the strongest possible case that this insurance claim photo is FRAUDULENT.
Cite exact scores. Be concise but devastating. Write 3-5 specific arguments.
Format: numbered list, each item starting with a bold fraud indicator name."""

    user_prompt = f"""FORENSIC EVIDENCE REPORT
========================
{evidence_summary}

CLAIM TEXT: "{claim_text or 'No claim description provided'}"

Build your prosecution case. Cite specific scores."""

    try:
        response = client.chat.complete(
            model="mistral-large-latest",
            max_tokens=600,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        arguments = response.choices[0].message.content
    except Exception as e:
        arguments = _prosecutor_fallback(scores)

    return {
        "arguments": arguments,
        "top_evidence": _get_top_evidence(scores),
        "agent": "PROSECUTOR"
    }


def run_defender(scores: dict, claim_text: str = "", image_description: str = "") -> dict:
    evidence_summary = _build_evidence_summary(scores)
    system_prompt = """You are the Defense Attorney in ARBITER's AI Forensic Tribunal.
Challenge the fraud allegations and argue that this insurance claim photo is AUTHENTIC.
Challenge AI scores, point out limitations, explain innocent explanations.
Format: numbered list, each item starting with a bold defense point."""

    user_prompt = f"""FORENSIC EVIDENCE REPORT
========================
{evidence_summary}

CLAIM TEXT: "{claim_text or 'No claim description provided'}"

Build your defense. Challenge suspicious findings."""

    try:
        response = client.chat.complete(
            model="mistral-large-latest",
            max_tokens=600,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        arguments = response.choices[0].message.content
    except Exception as e:
        arguments = _defender_fallback(scores)

    return {
        "arguments": arguments,
        "supporting_evidence": _get_clean_evidence(scores),
        "agent": "DEFENDER"
    }


def run_typology(scores: dict, claim_text: str = "") -> dict:
    evidence_summary = _build_evidence_summary(scores)
    system_prompt = """You are ARBITER's Fraud Typology Classifier.
Respond ONLY with valid JSON:
{
  "primary_type": "<GEN_AI|SPLICE_FRAUD|RECYCLED_CLAIM|PRE_EXISTING|GEO_MISMATCH|PHYSICS_FRAUD|METADATA_STRIPPED|AUTHENTIC>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one sentence>",
  "secondary_type": "<optional or null>"
}"""

    user_prompt = f"""FORENSIC SCORES:
{evidence_summary}

Classify the fraud type."""

    try:
        response = client.chat.complete(
            model="mistral-large-latest",
            max_tokens=200,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        raw = response.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()
        result = json.loads(raw)
    except Exception as e:
        result = _typology_fallback(scores)

    fraud_type = result.get("primary_type", "AUTHENTIC")
    return {
        "primary_type": fraud_type,
        "type_description": FRAUD_TYPES.get(fraud_type, "Unknown"),
        "confidence": result.get("confidence", 0.5),
        "reasoning": result.get("reasoning", ""),
        "secondary_type": result.get("secondary_type"),
        "agent": "TYPOLOGY_CLASSIFIER"
    }


def _build_evidence_summary(scores: dict) -> str:
    lines = []
    if "ela" in scores:
        ela = scores["ela"]
        lines.append(f"ELA Manipulation Score: {ela.get('fraud_score', 'N/A')} [{ela.get('label', '')}]")
    if "fft" in scores:
        fft = scores["fft"]
        lines.append(f"FFT AI-Generation Score: {fft.get('fraud_score', 'N/A')} [{fft.get('label', '')}]")
        lines.append(f"  Generator type: {fft.get('generator_type', 'N/A')}")
    if "phash" in scores:
        ph = scores["phash"]
        lines.append(f"pHash Duplicate Score: {ph.get('fraud_score', 'N/A')} [{ph.get('label', '')}]")
        if ph.get("matched_claim"):
            lines.append(f"  DUPLICATE: matches claim {ph.get('matched_claim')}")
    if "clip" in scores:
        clip = scores["clip"]
        lines.append(f"CLIP Context Score: {clip.get('fraud_score', 'N/A')} [{clip.get('label', '')}]")
    if "mahalanobis" in scores:
        m = scores["mahalanobis"]
        lines.append(f"DINOv2 Outlier Score: {m.get('fraud_score', 'N/A')} [{m.get('label', '')}]")
    if "sam" in scores:
        s = scores["sam"]
        lines.append(f"SAM Damage Severity: {s.get('severity_percent', 'N/A')}% [{s.get('severity_class', '')}]")
    if "temporal" in scores:
        t = scores["temporal"]
        lines.append(f"Temporal Forensics Score: {t.get('fraud_score', 'N/A')} [{t.get('label', '')}]")
        for flag in (t.get("flags") or []):
            lines.append(f"  FLAG: {flag}")
    return "\n".join(lines)


def _get_top_evidence(scores: dict) -> list:
    items = []
    for key, val in scores.items():
        if isinstance(val, dict) and "fraud_score" in val:
            items.append((key, val["fraud_score"], val.get("label", "")))
    items.sort(key=lambda x: x[1], reverse=True)
    return [{"signal": k, "score": s, "label": l} for k, s, l in items[:3]]


def _get_clean_evidence(scores: dict) -> list:
    items = []
    for key, val in scores.items():
        if isinstance(val, dict) and "fraud_score" in val:
            if val["fraud_score"] < 0.3:
                items.append({"signal": key, "score": val["fraud_score"], "label": val.get("label", "CLEAN")})
    return items


def _prosecutor_fallback(scores: dict) -> str:
    top = _get_top_evidence(scores)
    lines = []
    for i, ev in enumerate(top[:3], 1):
        lines.append(f"{i}. **{ev['signal'].upper()} anomaly** — Score: {ev['score']:.3f} ({ev['label']}). Consistent with fraudulent manipulation.")
    return "\n".join(lines) if lines else "1. **Insufficient data** — Multiple forensic signals unavailable."


def _defender_fallback(scores: dict) -> str:
    clean = _get_clean_evidence(scores)
    lines = []
    for i, ev in enumerate(clean[:3], 1):
        lines.append(f"{i}. **{ev['signal'].upper()} within normal bounds** — Score: {ev['score']:.3f}. Supports authenticity.")
    return "\n".join(lines) if lines else "1. **Limited clean signals** — Defense relies on absence of definitive manipulation proof."


def _typology_fallback(scores: dict) -> dict:
    max_score = 0
    primary = "AUTHENTIC"
    fft_score = scores.get("fft", {}).get("fraud_score", 0)
    ela_score = scores.get("ela", {}).get("fraud_score", 0)
    phash_score = scores.get("phash", {}).get("fraud_score", 0)
    temporal_score = scores.get("temporal", {}).get("fraud_score", 0)
    candidates = [
        ("GEN_AI", fft_score),
        ("SPLICE_FRAUD", ela_score),
        ("RECYCLED_CLAIM", phash_score),
        ("PRE_EXISTING", temporal_score),
    ]
    for type_name, score in candidates:
        if score > max_score:
            max_score = score
            primary = type_name
    if max_score < 0.3:
        primary = "AUTHENTIC"
    return {
        "primary_type": primary,
        "confidence": round(max_score, 3),
        "reasoning": f"Highest signal: {primary} at score {max_score:.3f}",
        "secondary_type": None
    }
