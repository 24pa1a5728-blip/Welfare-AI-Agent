"""
ocr_verification.py
--------------------
OCR and document verification for the Welfare Scheme AI Agent.

What this module does:
  1. Extracts text from uploaded PDFs and images using pytesseract + pdf2image
  2. Detects the document TYPE (Aadhaar, PAN, Income Certificate, etc.)
  3. Extracts key FIELDS from the detected document
  4. Validates extracted fields against the applicant's saved profile
  5. Stores the verification result in the database
  6. Exposes FastAPI endpoints for the frontend / AI agent to call

Install dependencies (run once in your venv):
  pip install pytesseract pdf2image Pillow
  # Also install system packages:
  # Ubuntu/Debian: sudo apt install tesseract-ocr poppler-utils
  # macOS:         brew install tesseract poppler
"""

import re
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from PIL import Image

# --------------------------------------------------
# Optional imports — graceful fallback if not installed
# --------------------------------------------------
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False


BASE_DIR = Path(__file__).resolve().parent

router = APIRouter(prefix="/documents", tags=["OCR & Verification"])


# ==================================================
# DATABASE HELPERS
# ==================================================

def get_db():
    conn = sqlite3.connect(BASE_DIR / "welfare.db")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_verification_table():
    """
    Create the document_verifications table if it does not exist.
    Call this once at startup (add to setup_db.py as well).
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS document_verifications (
        verification_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id       INTEGER NOT NULL,
        application_id    INTEGER NOT NULL,
        document_type     TEXT,
        extracted_fields  TEXT,
        verification_status TEXT DEFAULT 'pending',
        mismatch_fields   TEXT,
        verified_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (document_id) REFERENCES application_documents(document_id)
    )
    """)
    conn.commit()
    conn.close()


# ==================================================
# STEP 1 — EXTRACT RAW TEXT FROM FILE
# ==================================================

def extract_text_from_image(image_path: Path) -> str:
    """
    Run Tesseract OCR on a single image file.
    Returns the extracted text as a string.
    """
    if not TESSERACT_AVAILABLE:
        raise RuntimeError(
            "pytesseract is not installed. "
            "Run: pip install pytesseract  "
            "and install Tesseract: sudo apt install tesseract-ocr"
        )

    # --------------------------------------------------
    # Preprocessing improves OCR accuracy significantly
    # --------------------------------------------------
    image = Image.open(image_path)

    # Convert to grayscale
    image = image.convert("L")

    # Tesseract config:
    #   --oem 3  = LSTM neural net engine (most accurate)
    #   --psm 3  = Fully automatic page segmentation
    #   -l eng+hin  = English + Hindi (common on Indian government docs)
    custom_config = r"--oem 3 --psm 3 -l eng"

    text = pytesseract.image_to_string(image, config=custom_config)
    return text.strip()


def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Convert each PDF page to an image, then run Tesseract on each page.
    Returns all pages' text joined together.
    """
    if not PDF2IMAGE_AVAILABLE:
        raise RuntimeError(
            "pdf2image is not installed. "
            "Run: pip install pdf2image  "
            "and install poppler: sudo apt install poppler-utils"
        )

    if not TESSERACT_AVAILABLE:
        raise RuntimeError("pytesseract is not installed.")

    # Convert PDF pages to PIL images at 300 DPI for best OCR accuracy
    pages = convert_from_path(str(pdf_path), dpi=300)

    all_text = []
    for page_number, page_image in enumerate(pages, start=1):
        page_image = page_image.convert("L")  # grayscale
        custom_config = r"--oem 3 --psm 3 -l eng"
        page_text = pytesseract.image_to_string(page_image, config=custom_config)
        all_text.append(f"--- Page {page_number} ---\n{page_text.strip()}")

    return "\n\n".join(all_text)


def extract_text(file_path: Path) -> str:
    """
    Dispatch to the right extractor based on file extension.
    Supports: .pdf, .jpg, .jpeg, .png
    """
    ext = file_path.suffix.lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext in {".jpg", ".jpeg", ".png"}:
        return extract_text_from_image(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


# ==================================================
# STEP 2 — DETECT DOCUMENT TYPE
# ==================================================

# Each document type is identified by keywords that appear reliably in it.
DOCUMENT_TYPE_SIGNATURES = {
    "aadhaar": [
        "aadhaar", "uidai", "unique identification",
        "government of india", "आधार",          # Hindi
        "ఆధార్",                                 # Telugu
    ],
    "pan": [
        "permanent account number", "income tax department",
        "pan", "पैन",
    ],
    "income_certificate": [
        "income certificate", "annual income", "आय प्रमाण",
        "revenue department", "tehsildar", "taluk",
    ],
    "caste_certificate": [
        "caste certificate", "community certificate",
        "backward class", "obc", "scheduled caste", "scheduled tribe",
        "जाति प्रमाण",
    ],
    "land_record": [
        "patta", "khata", "khasra", "khatauni", "land record",
        "revenue record", "survey number", "landholding",
        "भूमि अभिलेख",
    ],
    "bank_passbook": [
        "passbook", "account number", "ifsc", "bank of",
        "savings account", "jan dhan",
    ],
    "disability_certificate": [
        "disability certificate", "person with disability",
        "दिव्यांग", "pwdms",
    ],
    "birth_certificate": [
        "birth certificate", "date of birth", "registrar of births",
        "municipal corporation",
    ],
    "mark_sheet": [
        "mark sheet", "marks obtained", "board of", "cbse", "icse",
        "percentage", "percentile", "result",
    ],
    "ration_card": [
        "ration card", "public distribution", "fair price shop",
        "bpl", "apl", "antyodaya",
    ],
}


def detect_document_type(text: str) -> str:
    """
    Score the extracted text against each document type's keyword signatures.
    Returns the best-matching type, or 'unknown' if nothing matches.
    """
    text_lower = text.lower()
    scores = {}

    for doc_type, keywords in DOCUMENT_TYPE_SIGNATURES.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[doc_type] = score

    if not scores:
        return "unknown"

    return max(scores, key=scores.get)


# ==================================================
# STEP 3 — EXTRACT FIELDS FROM DETECTED DOCUMENT
# ==================================================

def extract_aadhaar_fields(text: str) -> dict:
    """Extract name, DOB, gender, and Aadhaar number from Aadhaar card text."""

    fields = {}

    # Aadhaar number: 12 digits, often grouped as XXXX XXXX XXXX
    aadhaar_match = re.search(r"\b(\d{4}\s?\d{4}\s?\d{4})\b", text)
    if aadhaar_match:
        fields["aadhaar_number"] = aadhaar_match.group(1).replace(" ", "")

    # Date of birth: DD/MM/YYYY or DD-MM-YYYY or Year of Birth: YYYY
    dob_match = re.search(r"\b(\d{2}[/\-]\d{2}[/\-]\d{4})\b", text)
    if dob_match:
        fields["dob"] = dob_match.group(1)
    else:
        yob_match = re.search(r"year of birth[:\s]+(\d{4})", text, re.IGNORECASE)
        if yob_match:
            fields["year_of_birth"] = yob_match.group(1)

    # Gender
    if re.search(r"\bmale\b", text, re.IGNORECASE) and not re.search(r"\bfemale\b", text, re.IGNORECASE):
        fields["gender"] = "male"
    elif re.search(r"\bfemale\b", text, re.IGNORECASE):
        fields["gender"] = "female"

    # Name: line after "Name" label, or before DOB line
    name_match = re.search(r"(?:name|नाम)[:\s]+([A-Z][A-Za-z\s]{2,40})", text, re.IGNORECASE)
    if name_match:
        fields["name"] = name_match.group(1).strip()

    return fields


def extract_pan_fields(text: str) -> dict:
    """Extract PAN number and name from PAN card."""

    fields = {}

    # PAN format: 5 letters, 4 digits, 1 letter
    pan_match = re.search(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b", text)
    if pan_match:
        fields["pan_number"] = pan_match.group(1)

    # Name on card
    name_match = re.search(r"(?:name|नाम)[:\s]+([A-Z][A-Za-z\s]{2,40})", text, re.IGNORECASE)
    if name_match:
        fields["name"] = name_match.group(1).strip()

    return fields


def extract_income_certificate_fields(text: str) -> dict:
    """Extract annual income amount from income certificate."""

    fields = {}

    # Income amount — look for ₹ or Rs. followed by digits
    income_match = re.search(
        r"(?:annual income|income)[^\d]*(?:rs\.?|₹|inr)?\s*([\d,]+)",
        text, re.IGNORECASE
    )
    if income_match:
        amount_str = income_match.group(1).replace(",", "")
        try:
            fields["annual_income"] = int(amount_str)
        except ValueError:
            pass

    # Applicant name
    name_match = re.search(r"(?:name of|applicant)[:\s]+([A-Z][A-Za-z\s]{2,40})", text, re.IGNORECASE)
    if name_match:
        fields["name"] = name_match.group(1).strip()

    return fields


def extract_mark_sheet_fields(text: str) -> dict:
    """Extract percentage / percentile from a Class 12 mark sheet."""

    fields = {}

    # Percentage
    percent_match = re.search(r"(?:percentage|percent)[:\s]*([\d.]+)\s*%?", text, re.IGNORECASE)
    if percent_match:
        try:
            fields["percentage"] = float(percent_match.group(1))
        except ValueError:
            pass

    # Percentile (may appear separately)
    percentile_match = re.search(r"percentile[:\s]*([\d.]+)", text, re.IGNORECASE)
    if percentile_match:
        try:
            fields["percentile"] = float(percentile_match.group(1))
        except ValueError:
            pass

    # Roll number
    roll_match = re.search(r"roll\s*(?:no|number)[:\s]*([A-Z0-9\-]+)", text, re.IGNORECASE)
    if roll_match:
        fields["roll_number"] = roll_match.group(1).strip()

    return fields


def extract_land_record_fields(text: str) -> dict:
    """Extract landholding area from a land record / patta."""

    fields = {}

    # Hectares
    hect_match = re.search(r"([\d.]+)\s*(?:hectares?|ha\.?)\b", text, re.IGNORECASE)
    if hect_match:
        try:
            fields["landholding_hectares"] = float(hect_match.group(1))
        except ValueError:
            pass

    # Acres (convert to hectares: 1 acre = 0.4047 ha)
    acre_match = re.search(r"([\d.]+)\s*acres?\b", text, re.IGNORECASE)
    if acre_match:
        try:
            acres = float(acre_match.group(1))
            fields["landholding_hectares"] = round(acres * 0.4047, 4)
            fields["landholding_source_unit"] = "acres"
        except ValueError:
            pass

    return fields


# Master dispatcher
FIELD_EXTRACTORS = {
    "aadhaar":              extract_aadhaar_fields,
    "pan":                  extract_pan_fields,
    "income_certificate":   extract_income_certificate_fields,
    "mark_sheet":           extract_mark_sheet_fields,
    "land_record":          extract_land_record_fields,
}


def extract_fields(doc_type: str, text: str) -> dict:
    """Run the right field extractor for the detected document type."""
    extractor = FIELD_EXTRACTORS.get(doc_type)
    if extractor:
        return extractor(text)
    return {}


# ==================================================
# STEP 4 — VALIDATE AGAINST PROFILE
# ==================================================

def validate_against_profile(
    doc_type: str,
    extracted_fields: dict,
    profile: dict
) -> tuple[str, list[str]]:
    """
    Compare extracted document fields against the applicant's saved profile.

    Returns:
        (status, mismatches)
        status    = "verified" | "mismatch" | "partial" | "unverifiable"
        mismatches = list of human-readable mismatch descriptions
    """

    mismatches = []
    checks_run = 0

    # --------------------------------------------------
    # Aadhaar: check gender
    # --------------------------------------------------
    if doc_type == "aadhaar":
        if "gender" in extracted_fields and "gender" in profile:
            checks_run += 1
            doc_gender = extracted_fields["gender"].lower()
            profile_gender = str(profile.get("gender", "")).lower()
            if doc_gender and profile_gender and doc_gender != profile_gender:
                mismatches.append(
                    f"Gender mismatch: document says '{doc_gender}', "
                    f"profile says '{profile_gender}'"
                )

        # Check year of birth against age (approximate)
        if "year_of_birth" in extracted_fields and "age" in profile:
            checks_run += 1
            try:
                from datetime import datetime
                current_year = datetime.now().year
                doc_yob = int(extracted_fields["year_of_birth"])
                implied_age = current_year - doc_yob
                profile_age = int(profile["age"])
                if abs(implied_age - profile_age) > 2:
                    mismatches.append(
                        f"Age mismatch: document year of birth {doc_yob} implies "
                        f"age ~{implied_age}, but profile age is {profile_age}"
                    )
            except (ValueError, TypeError):
                pass

    # --------------------------------------------------
    # Income Certificate: check annual income
    # --------------------------------------------------
    elif doc_type == "income_certificate":
        if "annual_income" in extracted_fields and "annual_income" in profile:
            checks_run += 1
            doc_income = int(extracted_fields["annual_income"])
            profile_income = int(profile.get("annual_income", 0))
            # Allow 10% tolerance for rounding differences
            tolerance = profile_income * 0.10
            if abs(doc_income - profile_income) > tolerance:
                mismatches.append(
                    f"Income mismatch: document shows ₹{doc_income:,}, "
                    f"profile says ₹{profile_income:,}"
                )

    # --------------------------------------------------
    # Land Record: check landholding
    # --------------------------------------------------
    elif doc_type == "land_record":
        if "landholding_hectares" in extracted_fields and "landholding_hectares" in profile:
            checks_run += 1
            doc_land = float(extracted_fields["landholding_hectares"])
            profile_land = float(profile.get("landholding_hectares", 0))
            if abs(doc_land - profile_land) > 0.1:
                mismatches.append(
                    f"Landholding mismatch: document shows {doc_land} ha, "
                    f"profile says {profile_land} ha"
                )

    # --------------------------------------------------
    # Mark Sheet: just confirm we got a percentile
    # --------------------------------------------------
    elif doc_type == "mark_sheet":
        if "percentile" in extracted_fields or "percentage" in extracted_fields:
            checks_run += 1  # extractable, no profile field to compare against

    # --------------------------------------------------
    # Determine overall status
    # --------------------------------------------------
    if checks_run == 0:
        return "unverifiable", []

    if not mismatches:
        return "verified", []

    return "mismatch", mismatches


# ==================================================
# STEP 5 — FULL PIPELINE (orchestrates steps 1–4)
# ==================================================

def run_verification_pipeline(
    file_path: Path,
    application_id: int,
    document_id: int
) -> dict:
    """
    Full OCR + verification pipeline for one uploaded document.

    Returns a result dict that is also saved to document_verifications.
    """
    import json

    result = {
        "document_id":          document_id,
        "application_id":       application_id,
        "file_path":            str(file_path),
        "document_type":        "unknown",
        "extracted_fields":     {},
        "verification_status":  "pending",
        "mismatch_fields":      [],
        "error":                None
    }

    # --------------------------------------------------
    # 1. Extract text
    # --------------------------------------------------
    try:
        raw_text = extract_text(file_path)
    except Exception as e:
        result["error"] = f"Text extraction failed: {str(e)}"
        result["verification_status"] = "error"
        _save_verification(result)
        return result

    if not raw_text.strip():
        result["error"] = "No text could be extracted from the document."
        result["verification_status"] = "unverifiable"
        _save_verification(result)
        return result

    # --------------------------------------------------
    # 2. Detect document type
    # --------------------------------------------------
    doc_type = detect_document_type(raw_text)
    result["document_type"] = doc_type

    # --------------------------------------------------
    # 3. Extract fields
    # --------------------------------------------------
    extracted = extract_fields(doc_type, raw_text)
    result["extracted_fields"] = extracted

    # --------------------------------------------------
    # 4. Load applicant profile
    # --------------------------------------------------
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT p.*
    FROM profiles p
    JOIN applications a ON p.profile_id = a.profile_id
    WHERE a.application_id = ?
    """, (application_id,))

    profile_row = cursor.fetchone()
    conn.close()

    if profile_row is None:
        result["error"] = "Could not find profile linked to this application."
        result["verification_status"] = "error"
        _save_verification(result)
        return result

    profile = dict(profile_row)

    # --------------------------------------------------
    # 5. Validate against profile
    # --------------------------------------------------
    status, mismatches = validate_against_profile(doc_type, extracted, profile)
    result["verification_status"] = status
    result["mismatch_fields"] = mismatches

    # --------------------------------------------------
    # 6. Save to DB
    # --------------------------------------------------
    _save_verification(result)

    return result


def _save_verification(result: dict):
    """Save a verification result to the document_verifications table."""
    import json

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO document_verifications
    (document_id, application_id, document_type, extracted_fields, verification_status, mismatch_fields)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(document_id) DO UPDATE SET
        document_type       = excluded.document_type,
        extracted_fields    = excluded.extracted_fields,
        verification_status = excluded.verification_status,
        mismatch_fields     = excluded.mismatch_fields,
        verified_at         = CURRENT_TIMESTAMP
    """, (
        result["document_id"],
        result["application_id"],
        result["document_type"],
        json.dumps(result["extracted_fields"]),
        result["verification_status"],
        json.dumps(result["mismatch_fields"])
    ))

    conn.commit()
    conn.close()


# ==================================================
# FASTAPI ENDPOINTS
# ==================================================

@router.post(
    "/applications/{application_id}/documents/{document_id}/verify",
    summary="Run OCR and verify a single document"
)
def verify_document(application_id: int, document_id: int):
    """
    Trigger OCR + field extraction + profile validation for one uploaded document.

    Steps:
      1. Looks up the uploaded file path from application_documents
      2. Runs OCR to extract text
      3. Detects what kind of document it is
      4. Extracts key fields (name, DOB, income, etc.)
      5. Compares against the applicant's saved profile
      6. Stores and returns the result

    Verification statuses:
      - verified       → extracted fields match the profile
      - mismatch       → fields were found but do not match the profile
      - partial        → some fields matched, others did not
      - unverifiable   → document type was detected but no comparable fields found
      - unknown        → document type could not be identified
      - error          → OCR or processing failed
    """

    conn = get_db()
    cursor = conn.cursor()

    # Get document record
    cursor.execute("""
    SELECT d.document_name, d.document_status, a.application_id
    FROM application_documents d
    JOIN applications a ON d.application_id = a.application_id
    WHERE d.document_id = ? AND d.application_id = ?
    """, (document_id, application_id))

    doc = cursor.fetchone()
    conn.close()

    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc["document_status"] != "uploaded":
        raise HTTPException(
            status_code=400,
            detail="Document must be an uploaded file (status='uploaded') to run OCR. "
                   "Database-only name records cannot be verified."
        )

    file_path = BASE_DIR / "uploads" / doc["document_name"]

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Uploaded file not found on disk: {doc['document_name']}"
        )

    if not TESSERACT_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="OCR service unavailable. "
                   "Install: pip install pytesseract  and  sudo apt install tesseract-ocr"
        )

    result = run_verification_pipeline(file_path, application_id, document_id)
    return result


@router.post(
    "/applications/{application_id}/documents/verify-all",
    summary="Run OCR and verify ALL uploaded documents for an application"
)
def verify_all_documents(application_id: int):
    """
    Batch: run OCR verification on every uploaded document for this application.
    Useful to call after all documents have been uploaded.
    """

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT document_id, document_name, document_status
    FROM application_documents
    WHERE application_id = ? AND document_status = 'uploaded'
    """, (application_id,))

    docs = cursor.fetchall()
    conn.close()

    if not docs:
        raise HTTPException(
            status_code=404,
            detail="No uploaded documents found for this application."
        )

    results = []
    for doc in docs:
        file_path = BASE_DIR / "uploads" / doc["document_name"]
        if not file_path.exists():
            results.append({
                "document_id": doc["document_id"],
                "document_name": doc["document_name"],
                "verification_status": "error",
                "error": "File not found on disk"
            })
            continue

        result = run_verification_pipeline(file_path, application_id, doc["document_id"])
        results.append(result)

    # Summary counts
    status_counts = {}
    for r in results:
        s = r.get("verification_status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "application_id": application_id,
        "documents_checked": len(results),
        "summary": status_counts,
        "results": results
    }


@router.get(
    "/applications/{application_id}/documents/verification-status",
    summary="Get verification status of all documents for an application"
)
def get_verification_status(application_id: int):
    """
    Returns the latest verification result for every document
    attached to this application. Use this to show the citizen
    which documents are verified, mismatched, or still pending.
    """
    import json

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        d.document_id,
        d.document_name,
        d.document_status,
        v.document_type,
        v.extracted_fields,
        v.verification_status,
        v.mismatch_fields,
        v.verified_at
    FROM application_documents d
    LEFT JOIN document_verifications v ON d.document_id = v.document_id
    WHERE d.application_id = ?
    ORDER BY d.document_id
    """, (application_id,))

    rows = cursor.fetchall()
    conn.close()

    documents = []
    for row in rows:
        doc = dict(row)

        # Parse JSON fields back to Python objects
        if doc.get("extracted_fields"):
            try:
                doc["extracted_fields"] = json.loads(doc["extracted_fields"])
            except (json.JSONDecodeError, TypeError):
                pass

        if doc.get("mismatch_fields"):
            try:
                doc["mismatch_fields"] = json.loads(doc["mismatch_fields"])
            except (json.JSONDecodeError, TypeError):
                pass

        # Not yet verified
        if doc["verification_status"] is None:
            doc["verification_status"] = "pending"

        documents.append(doc)

    # Overall application readiness
    statuses = [d["verification_status"] for d in documents]
    all_good = all(s in ("verified", "unverifiable") for s in statuses)
    any_mismatch = any(s == "mismatch" for s in statuses)
    any_pending = any(s == "pending" for s in statuses)

    if all_good:
        overall = "ready_to_submit"
    elif any_mismatch:
        overall = "has_mismatches"
    elif any_pending:
        overall = "verification_pending"
    else:
        overall = "requires_attention"

    return {
        "application_id": application_id,
        "overall_status": overall,
        "document_count": len(documents),
        "documents": documents
    }


@router.get(
    "/applications/{application_id}/documents/{document_id}/verification",
    summary="Get the verification result for a single document"
)
def get_document_verification(application_id: int, document_id: int):
    """Get the stored OCR verification result for one document."""
    import json

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT v.*, d.document_name
    FROM document_verifications v
    JOIN application_documents d ON v.document_id = d.document_id
    WHERE v.document_id = ? AND v.application_id = ?
    """, (document_id, application_id))

    row = cursor.fetchone()
    conn.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="No verification record found. Run /verify first."
        )

    result = dict(row)

    if result.get("extracted_fields"):
        try:
            result["extracted_fields"] = json.loads(result["extracted_fields"])
        except (json.JSONDecodeError, TypeError):
            pass

    if result.get("mismatch_fields"):
        try:
            result["mismatch_fields"] = json.loads(
                result["mismatch_fields"]
            )
        except (json.JSONDecodeError, TypeError):
            pass

    return result
