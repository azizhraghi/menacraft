# Person 3 — Complete Deep Dive

> Your role: **The Context & Intelligence Specialist** (Layer 3 + Layer 4)
> Your files: `temporal.py` + `debate.py`

---

## THE BIG PICTURE: Where You Fit

```
Image + Claim Text arrives at /analyze endpoint
         │
         ├─ Person 1 runs forensics.py ──► ELA score, FFT score, pHash score
         ├─ Person 2 runs semantic.py  ──► CLIP score, DINOv2 score, SAM severity
         │
         ├─ YOU run temporal.py ───────► Temporal score (EXIF + GPS + metadata)
         │     "Is the photo's history suspicious?"
         │
         ├─ YOU run debate.py ─────────► Prosecutor arguments, Defender arguments,
         │     "What does the AI think?"      Fraud type classification
         │
         └─ Person 4 runs verdict.py ──► Final 0-100 risk score + action
```

**Your modules are the brain of the system.** Layers 1 & 2 produce raw numbers. Your Layer 3 adds *context* (when/where was the photo taken?), and your Layer 4 adds *reasoning* (what does all the evidence mean together?).

---

# PART 1: `temporal.py` — Layer 3

## What This Module Does (in plain English)

Every digital photo carries invisible metadata — the **EXIF data**. When you take a photo with your phone, it secretly records:
- **When** the photo was taken (date + time)
- **Where** it was taken (GPS coordinates)
- **What device** took it (camera brand, model)
- **What software** touched it (Photoshop, filters, etc.)

Fraudsters often don't know this metadata exists, or they forget to strip it. Your module **reads this hidden data and catches liars**.

---

## Function-by-Function Breakdown

### 1. `run_temporal_analysis()` — The Orchestrator

```python
def run_temporal_analysis(image: Image.Image, claim_date: str = None,
                           claim_location: str = None) -> dict:
```

**What it receives:**
- `image` — The PIL Image object (the actual photo pixels + metadata)
- `claim_date` — The date the claimant says the incident happened (e.g. `"2026-03-15"`)
- `claim_location` — Where they say it happened (optional, currently unused for geocoding)

**What it does (step by step):**

```python
exif_data = _extract_exif(image)           # Step 1: Read all hidden metadata
timestamp_result = _analyze_timestamp(exif_data, claim_date)  # Step 2: Check dates
gps_result = _analyze_gps(exif_data, claim_location)          # Step 3: Check location
metadata_result = _analyze_metadata_integrity(exif_data, image) # Step 4: Check tampering
```

Then it combines the three sub-scores:

```python
scores = [timestamp_result["fraud_score"],    # e.g. [0.75, 0.0, 0.6]
          gps_result["fraud_score"],
          metadata_result["fraud_score"]]

combined_score = max(scores) * 0.6 + sum(scores) / len(scores) * 0.4
```

#### The Formula Explained

```
combined = (WORST score × 0.6) + (AVERAGE of all × 0.4)
```

**Why this formula?** Because one really bad signal should dominate. Example:

| Scenario | Timestamp | GPS | Metadata | Max | Avg | Combined |
|----------|-----------|-----|----------|-----|-----|----------|
| Photo is 60 days old, has Photoshop | 0.75 | 0.0 | 0.6 | 0.75 | 0.45 | **0.63** |
| Everything clean | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | **0.0** |
| No EXIF at all | 0.65 | 0.3 | 0.5 | 0.65 | 0.483 | **0.583** |
| GPS is (0,0) spoofed | 0.0 | 0.8 | 0.0 | 0.8 | 0.267 | **0.587** |

Then it collects **flags** — human-readable warnings:

```python
if timestamp_result["fraud_score"] > 0.4:
    flags.append(timestamp_result.get("flag", "Timestamp anomaly"))
```

Only scores above 0.4 become flags. This prevents noise from low-confidence findings.

**Final output structure:**
```python
{
    "fraud_score": 0.583,           # The combined score (0-1)
    "label": "MEDIUM_RISK",         # Human label
    "flags": ["No EXIF data — metadata may have been stripped"],
    "timestamp": { ... },           # Full timestamp analysis
    "gps": { ... },                 # Full GPS analysis
    "metadata_integrity": { ... },  # Full metadata analysis
    "raw_exif_summary": { ... },    # Clean summary for display
    "method": "EXIF DateTimeOriginal + GPS + Metadata integrity analysis"
}
```

---

### 2. `_extract_exif()` — The Metadata Reader

This is the **data extraction** layer. It reads the raw EXIF bytes embedded in the image.

```python
def _extract_exif(image: Image.Image) -> dict:
```

**Step by step:**

```python
exif_bytes = image.info.get("exif", b"")   # PIL stores EXIF as raw bytes in .info
if not exif_bytes:
    return result                           # No EXIF → return defaults (all None)

exif_dict = piexif.load(exif_bytes)         # piexif parses bytes into a dict
```

**What `piexif.load()` returns** — a dict with these keys:
```python
{
    "0th": { ... },    # IFD0 — basic image info (make, model, software)
    "Exif": { ... },   # Exif IFD — photo-specific (date taken, exposure, etc.)
    "GPS": { ... },    # GPS IFD — coordinates, altitude, direction
    "1st": { ... },    # Thumbnail IFD
}
```

Then it extracts specific fields:

```python
# Date the photo was ORIGINALLY taken (not modified, not uploaded)
dt_orig = exif_ifd.get(piexif.ExifIFD.DateTimeOriginal)

# Camera info from IFD0
make = ifd0.get(piexif.ImageIFD.Make)      # e.g. "Apple", "Samsung"
model = ifd0.get(piexif.ImageIFD.Model)    # e.g. "iPhone 15 Pro"
software = ifd0.get(piexif.ImageIFD.Software)  # e.g. "Adobe Photoshop"
```

**GPS extraction** uses a helper function `_convert_gps()`:

```python
lat = _convert_gps(gps_ifd.get(piexif.GPSIFD.GPSLatitude),
                   gps_ifd.get(piexif.GPSIFD.GPSLatitudeRef, b'N'))
```

---

### 3. `_convert_gps()` — GPS Coordinate Math

EXIF stores GPS in a weird format: **degrees, minutes, seconds** as rational numbers (fractions).

```python
# EXIF stores: ((36, 1), (7, 1), (3891, 100))
# Meaning:     36°      7'     38.91"

degrees = coord[0][0] / coord[0][1]    # 36/1 = 36
minutes = coord[1][0] / coord[1][1] / 60    # 7/1 / 60 = 0.1167
seconds = coord[2][0] / coord[2][1] / 3600  # 3891/100 / 3600 = 0.01081
decimal = degrees + minutes + seconds        # 36.12751
```

Then it checks the hemisphere reference:
```python
if ref_str in ['S', 'W']:
    decimal = -decimal   # South and West are negative coordinates
```

So `36°7'38.91"N` becomes `36.12751` and `36°7'38.91"S` becomes `-36.12751`.

---

### 4. `_analyze_timestamp()` — Date Detective

This is where you catch **pre-existing damage** and **timeline fraud**.

**Five possible scenarios:**

#### Scenario A: No EXIF at all
```python
if not exif_data["has_exif"]:
    return {"fraud_score": 0.65, ...}
```
→ Score **0.65** — suspicious because legitimate photos usually have EXIF. Stripping metadata is a common fraud tactic.

#### Scenario B: EXIF exists but no DateTimeOriginal  
```python
if not exif_data["datetime_original"]:
    return {"fraud_score": 0.5, ...}
```
→ Score **0.5** — the photo has some metadata but the capture time is specifically missing.

#### Scenario C: Photo taken AFTER the claim date
```python
if days_diff < 0:      # claim_date - photo_date = negative
    fraud_score = 0.8
    flag = f"Photo timestamp is {abs(days_diff)} days AFTER claim date"
```
→ Score **0.8** — How can the photo exist before the incident was reported? Very suspicious.

Example: Claim date is March 1, photo taken March 5 → `days_diff = -4` → 🔴

#### Scenario D: Photo taken more than 30 days before claim
```python
elif days_diff > 30:
    fraud_score = 0.75
    flag = f"Photo taken {days_diff} days before claimed incident"
```
→ Score **0.75** — The photo is very old. If someone claims damage from last week but the photo is from 2 months ago, this is likely **pre-existing damage**.

#### Scenario E: Photo taken 7-30 days before claim
```python
elif days_diff > 7:
    fraud_score = 0.35
```
→ Score **0.35** — Minor discrepancy. People sometimes wait a week to file, so not necessarily fraud.

#### Scenario F: Photo within 7 days of claim (or no claim_date provided)
→ Score **0.0** — Normal timeline, nothing suspicious.

---

### 5. `_analyze_gps()` — Location Detective

**Three outcomes:**

#### No GPS data
```python
if not exif_data["has_gps"]:
    return {"fraud_score": 0.3, ...}
```
→ Score **0.3** — mildly suspicious. Many photos lack GPS (desktop screenshots, some camera settings).

#### Null Island Detection (0°N, 0°E)
```python
if abs(lat) < 0.01 and abs(lon) < 0.01:
    fraud_score = 0.8
    flag = "GPS coordinates are 0,0 — likely spoofed"
```
→ Score **0.8** — Coordinates (0, 0) is in the Atlantic Ocean off the coast of Africa. No car accident happens there. This is the classic sign of a GPS spoofing tool that defaults to (0, 0).

The threshold `0.01` degrees ≈ 1.1 km, so anything within a 1km radius of null island triggers this.

#### Valid GPS present
→ Score **0.0** — GPS exists and looks legitimate. Currently no distance comparison (would need geocoding API for `claim_location`).

---

### 6. `_analyze_metadata_integrity()` — Tampering Detective

This checks for signs the image was **edited** or **generated**:

```python
suspicious_software = ["photoshop", "gimp", "lightroom", "midjourney",
                       "stable diffusion", "dall-e", "adobe", "canva"]
```

If the EXIF `Software` field contains any of these → Score **+0.6**

Why these specifically?
- **Photoshop/GIMP/Lightroom** → image editing (could have altered damage)
- **Midjourney/Stable Diffusion/DALL-E** → AI-generated image (complete fake)
- **Adobe/Canva** → digital manipulation tools

Also checks:
```python
if exif_data["has_exif"] and not exif_data["make"]:
    score += 0.25
    flags.append("Camera make/model missing")
```
→ If EXIF exists but no camera brand, the image might be a synthetic creation or has been processed through a tool that strips device info.

---

### 7. `_score_label()` — Risk Tier Labels

```python
if score >= 0.75: return "HIGH_RISK"
elif score >= 0.45: return "MEDIUM_RISK"  
elif score >= 0.2:  return "LOW_RISK"
else:               return "CLEAN"
```

Simple thresholds. These labels appear in the frontend UI and PDF report.

---

# PART 2: `debate.py` — Layer 4

## What This Module Does (in plain English)

Your Layer 4 is the **most unique part** of the entire project. It takes all the raw scores from Layers 1-3 and feeds them to an LLM (Mistral) acting as **two adversarial agents**:

1. **Prosecutor** 🔴 — Builds the strongest case that the claim is FRAUDULENT
2. **Defender** 🟢 — Challenges every allegation and argues for AUTHENTICITY
3. **Typology Classifier** 📋 — Labels the specific type of fraud (if any)

This is called an **adversarial debate pattern** — it's the same concept as a courtroom trial. By having two opposing viewpoints, the system avoids confirmation bias.

---

## The Mistral Client

```python
from mistralai import Mistral
client = Mistral(api_key=os.environ.get("MISTRAL_API_KEY", ""))
```

This creates the API client. It uses the `mistralai` Python SDK to call Mistral's `mistral-large-latest` model. Every LLM call costs API credits.

---

## The Fraud Type Dictionary

```python
FRAUD_TYPES = {
    "GEN_AI":           "Fully AI-generated damage image",
    "SPLICE_FRAUD":     "Real vehicle with digitally inserted damage",
    "RECYCLED_CLAIM":   "Previously submitted image reused",
    "PRE_EXISTING":     "Pre-existing damage as new incident",
    "GEO_MISMATCH":     "Location/timestamp inconsistent",
    "PHYSICS_FRAUD":    "Damage pattern physically impossible",
    "METADATA_STRIPPED": "Metadata removed to hide origin",
    "AUTHENTIC":        "No significant fraud indicators"
}
```

These are the **8 possible verdicts** the system can assign. Each maps a code to a human-readable description.

---

## Function-by-Function Breakdown

### 1. `run_prosecutor()` — The Accusation

```python
def run_prosecutor(scores: dict, claim_text: str = "", image_description: str = "") -> dict:
```

**What `scores` looks like** when it arrives:
```python
{
    "ela":          {"fraud_score": 0.35, "label": "LOW_RISK", ...},
    "fft":          {"fraud_score": 0.85, "label": "HIGH_RISK", "generator_type": "DIFFUSION_MODEL"},
    "phash":        {"fraud_score": 0.0,  "label": "UNIQUE", ...},
    "clip":         {"fraud_score": 0.1,  "label": "CLEAN", ...},
    "mahalanobis":  {"fraud_score": 0.3,  "label": "LOW_RISK", ...},
    "sam":          {"severity_percent": 15.2, "severity_class": "MINOR", ...},
    "temporal":     {"fraud_score": 0.65, "label": "MEDIUM_RISK", "flags": ["No EXIF data"], ...}
}
```

**Step 1:** Build the evidence summary (formats all scores into readable text):
```python
evidence_summary = _build_evidence_summary(scores)
```

This produces text like:
```
ELA Manipulation Score: 0.35 [LOW_RISK]
FFT AI-Generation Score: 0.85 [HIGH_RISK]
  Generator type: DIFFUSION_MODEL
pHash Duplicate Score: 0.0 [UNIQUE]
CLIP Context Score: 0.1 [CLEAN]
DINOv2 Outlier Score: 0.3 [LOW_RISK]
SAM Damage Severity: 15.2% [MINOR]
Temporal Forensics Score: 0.65 [MEDIUM_RISK]
  FLAG: No EXIF data — metadata may have been stripped
```

**Step 2:** Send to the LLM with a prosecutor persona:

```python
system_prompt = """You are the Prosecutor in ARBITER's AI Forensic Tribunal.
Build the strongest possible case that this insurance claim photo is FRAUDULENT.
Cite exact scores. Be concise but devastating. Write 3-5 specific arguments.
Format: numbered list, each item starting with a bold fraud indicator name."""
```

**Step 3:** The LLM returns something like:
```
1. **FFT AI-Generation Signal** — Score: 0.850 (HIGH_RISK). The frequency analysis 
   reveals a DIFFUSION_MODEL fingerprint, consistent with AI-generated imagery...
2. **Metadata Absence** — Temporal score: 0.650 (MEDIUM_RISK). No EXIF data found, 
   suggesting deliberate metadata scrubbing to conceal image origin...
3. **Damage Inconsistency** — SAM reports only 15.2% surface damage (MINOR), 
   yet if this were a genuine high-speed collision...
```

**Step 4:** If the LLM call fails (network error, API down), use the fallback:
```python
except Exception as e:
    arguments = _prosecutor_fallback(scores)
```

The fallback generates a simple numbered list from the top 3 highest scores — no LLM needed.

**Output:**
```python
{
    "arguments": "1. **FFT AI-Generation Signal** — ...",
    "top_evidence": [
        {"signal": "fft", "score": 0.85, "label": "HIGH_RISK"},
        {"signal": "temporal", "score": 0.65, "label": "MEDIUM_RISK"},
        ...
    ],
    "agent": "PROSECUTOR"
}
```

---

### 2. `run_defender()` — The Defense

Same structure as prosecutor but with the **opposite persona**:

```python
system_prompt = """You are the Defense Attorney in ARBITER's AI Forensic Tribunal.
Challenge the fraud allegations and argue that this insurance claim photo is AUTHENTIC.
Challenge AI scores, point out limitations, explain innocent explanations."""
```

The LLM will produce counter-arguments:
```
1. **FFT Limitations** — While FFT reports 0.850, frequency artifacts can also result 
   from heavy JPEG compression, social media re-uploads, or phone camera HDR processing...
2. **Metadata Absence is Common** — Many messaging apps (WhatsApp, Telegram) strip EXIF 
   data automatically during photo sharing. Score 0.650 does not prove deliberate scrubbing...
```

The defender's fallback (`_defender_fallback`) lists signals that **support** authenticity — those with scores below 0.3.

---

### 3. `run_typology()` — The Classifier

This asks the LLM to output **structured JSON** (not free text):

```python
system_prompt = """You are ARBITER's Fraud Typology Classifier.
Respond ONLY with valid JSON:
{
  "primary_type": "<GEN_AI|SPLICE_FRAUD|RECYCLED_CLAIM|...>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one sentence>",
  "secondary_type": "<optional or null>"
}"""
```

**JSON parsing with safety:**
```python
raw = response.choices[0].message.content.strip()

# LLMs often wrap JSON in ```json ... ``` markdown fences
if "```" in raw:
    raw = raw.split("```")[1].replace("json", "").strip()

result = json.loads(raw)
```

**Why three steps?** LLMs are unpredictable. Sometimes they return:
- Clean JSON: `{"primary_type": "GEN_AI", ...}` ✅
- Markdown-wrapped: `` ```json\n{"primary_type": "GEN_AI"}\n``` `` ← needs unwrapping
- With explanation: `"Here's my analysis: {"primary_type": ...}"` ← needs extraction

The `split("```")[1]` handles the markdown case: splitting by triple backticks gives `["", "json\n{...}", ""]`, so index `[1]` is the content inside the fences.

**Fallback** (`_typology_fallback`) — deterministic mapping without any LLM:

```python
candidates = [
    ("GEN_AI",        fft_score),      # High FFT → AI-generated
    ("SPLICE_FRAUD",  ela_score),      # High ELA → digitally edited
    ("RECYCLED_CLAIM", phash_score),   # High pHash → duplicate image
    ("PRE_EXISTING",  temporal_score), # High temporal → old photo
]
# Pick whichever has the highest score
```

This ensures the system **always produces a fraud type label**, even without API access.

---

### 4. `_build_evidence_summary()` — Formatting All Scores for the LLM

This function translates the raw score dictionaries into human-readable text that the LLM can understand:

```python
if "ela" in scores:
    ela = scores["ela"]
    lines.append(f"ELA Manipulation Score: {ela.get('fraud_score', 'N/A')} [{ela.get('label', '')}]")
```

It handles every signal type (ELA, FFT, pHash, CLIP, DINOv2, SAM, Temporal) and includes special details:
- FFT: includes `generator_type` (DIFFUSION_MODEL, GAN_MODEL, etc.)
- pHash: if a duplicate match is found, includes the matched claim ID
- Temporal: lists all forensic flags

**The output of this function is what the LLM "sees" as evidence.** This is essentially the "case file" handed to the AI lawyer.

---

### 5. `_get_top_evidence()` and `_get_clean_evidence()` — Signal Sorting

```python
# Top evidence: sorted by score, highest first, take top 3
items.sort(key=lambda x: x[1], reverse=True)
return items[:3]  # → [("fft", 0.85, "HIGH_RISK"), ("temporal", 0.65, "MEDIUM_RISK"), ...]

# Clean evidence: everything below 0.3
if val["fraud_score"] < 0.3:
    items.append(...)
```

These are used by:
- Prosecutor → shows `top_evidence` (most damning signals)
- Defender → shows `supporting_evidence` (cleanest signals)

---

## How main.py Calls Your Code

In [main.py](file:///c:/Users/aziz/OneDrive/Bureau/arbiter/arbiter_backend/backend/main.py#L79-L97), your code is called in two phases:

```python
# Phase 1: Your Layer 3 (temporal analysis)
temporal_result = run_temporal_analysis(
    pil_image,
    claim_date=claim_date if claim_date else None,
    claim_location=claim_location if claim_location else None
)

# All layer scores get assembled into a dict
layer_scores = {
    "ela": ela_result,      # From Person 1
    "fft": fft_result,      # From Person 1
    "phash": phash_result,  # From Person 1
    "clip": clip_result,    # From Person 2
    "mahalanobis": mahal_result,  # From Person 2
    "sam": sam_result,      # From Person 2
    "temporal": temporal_result,  # ← YOUR Layer 3
}

# Phase 2: Your Layer 4 (LLM debate)
prosecutor_result = run_prosecutor(layer_scores, claim_text)
defender_result = run_defender(layer_scores, claim_text)
typology_result = run_typology(layer_scores, claim_text)
```

Your temporal score feeds into:
1. The **verdict engine** (weighted at 12% of the final score)
2. The **LLM debate** (the prosecutor/defender see it as evidence)
3. The **PDF report** (temporal flags appear in "Detailed Technical Findings")
4. The **frontend** (temporal score bar, forensic flags section, EXIF grid)

---

## Complete Data Flow Diagram

```
┌─────────────────────────────────────────────────────────┐
│                   User uploads image                     │
│              + claim_text, claim_date, etc.              │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
            ┌─── temporal.py ───┐
            │                   │
            │  _extract_exif()  │─── reads EXIF bytes ──► {datetime, gps, make, software}
            │        │          │
            │        ▼          │
            │  _analyze_        │
            │  timestamp()      │─── compares photo date vs claim date ──► fraud_score
            │        │          │
            │  _analyze_gps()   │─── checks for Null Island, validates coords ──► fraud_score
            │        │          │
            │  _analyze_        │
            │  metadata_        │
            │  integrity()      │─── checks for Photoshop/AI software ──► fraud_score
            │        │          │
            │        ▼          │
            │  Combined score   │─── max×0.6 + avg×0.4 ──► final temporal fraud_score
            │  + flags list     │
            └────────┬──────────┘
                     │
                     ▼
         ┌── All layer_scores assembled ──┐
         │  ela, fft, phash, clip,        │
         │  mahalanobis, sam, temporal     │
         └───────────┬────────────────────┘
                     │
                     ▼
            ┌─── debate.py ────┐
            │                  │
            │ _build_evidence_ │─── formats all scores as human text
            │ summary()        │
            │       │          │
            │       ├──────────┤
            │       │          │
            │       ▼          ▼
            │  run_prosecutor  run_defender
            │  "Build fraud    "Challenge the
            │   case"           fraud case"
            │       │          │
            │       ▼          │
            │  run_typology    │─── classify as GEN_AI / RECYCLED / etc.
            │       │          │
            │       ▼          │
            │  [If API fails:  │
            │   use fallback]  │
            └───────┬──────────┘
                    │
                    ▼
            verdict.py uses your
            temporal_score (12% weight)
            + typology label
                    │
                    ▼
            Final output: 0-100 risk score
            + APPROVE / FLAG / REJECT
```

---

## Key Concepts to Explain in a Presentation

### 1. "Why EXIF analysis for fraud detection?"
> "Every smartphone embeds hidden metadata in photos — timestamps, GPS, camera model, software. Fraudsters often submit recycled old photos or AI-generated images. Our temporal forensics layer examines this metadata to detect timeline inconsistencies, stripped metadata (suggesting cover-up), and editing software that indicates manipulation."

### 2. "Why an adversarial debate instead of just a score?"
> "A single AI opinion creates confirmation bias. Our system uses two adversarial LLM agents — a Prosecutor who builds the fraud case and a Defender who challenges it. This mirrors the legal system and produces balanced, explainable decisions. The claims adjuster can read both arguments and make an informed judgment."

### 3. "What happens if the AI API is down?"
> "Every LLM call has a deterministic fallback. The prosecutor fallback lists the top 3 highest fraud signals with scores. The defender fallback lists all clean signals. The typology fallback maps the highest signal directly to a fraud type. The system never crashes — it degrades gracefully."

### 4. "How does the scoring work?"
> "Each sub-check (timestamp, GPS, metadata) produces a score from 0 to 1. We combine them using `max × 0.6 + average × 0.4`. This means one bad signal carries 60% of the weight — because in fraud detection, a single red flag matters more than the average. For example, if the GPS shows Null Island (0,0), that alone scores 0.8 regardless of other checks."

### 5. "What is Null Island?"
> "Null Island is the point at coordinates 0°N, 0°E — in the middle of the Atlantic Ocean. GPS spoofing tools often default to these coordinates. If a car accident photo has GPS coordinates of (0, 0), it's obviously fake because no roads exist there."
