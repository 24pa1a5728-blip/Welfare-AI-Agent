import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from pydantic import BaseModel


from ocr_verification import (
    router as ocr_router,
    ensure_verification_table
)


BASE_DIR = Path(__file__).resolve().parent

from ocr_verification import router as ocr_router, ensure_verification_table


app = FastAPI(
    title="Welfare Scheme AI Agent",
    description="Backend API for welfare scheme discovery, eligibility matching, and application management.",
    version="1.0.0"

)


app.include_router(ocr_router)

ensure_verification_table()



# --------------------------------------------------
# Valid Application Statuses
# --------------------------------------------------

VALID_STATUSES = [
    "draft",
    "submitted",
    "under_review",
    "approved",
    "rejected"
]


# --------------------------------------------------
# 1. User Profile
# --------------------------------------------------

class UserProfile(BaseModel):

    age: int
    gender: str
    state: str
    district: str
    annual_income: int
    marital_status: str
    occupation: str

    disability: bool
    farmer: bool
    pension: bool

    landholding_hectares: float
    land_acquisition_date: str
    land_acquired_by_succession: bool

    institutional_landholder: bool
    constitutional_post_holder: bool
    minister_or_legislator: bool
    mayor_or_panchayat_chairperson: bool

    government_employee: bool
    government_employee_group: str

    monthly_pension: int
    income_tax_payer: bool

    practicing_professional: bool
    nri: bool


# --------------------------------------------------
# 2. Application
# --------------------------------------------------

class Application(BaseModel):

    profile_id: int
    scheme_id: str
    applicant_name: str


# --------------------------------------------------
# 3. Scheme Answer Models
# --------------------------------------------------

class SchemeAnswer(BaseModel):

    profile_id: int
    field: str
    value: str


class SchemeAnswers(BaseModel):

    profile_id: int
    answers: dict[str, str]


# --------------------------------------------------
# 4. Application Document Model
# --------------------------------------------------

class ApplicationDocument(BaseModel):

    application_id: int
    document_name: str


# --------------------------------------------------
# HELPER: Get DB Connection
# --------------------------------------------------

def get_db():
    connection = sqlite3.connect(BASE_DIR / "welfare.db")
    connection.row_factory = sqlite3.Row
    return connection


# --------------------------------------------------
# HELPER: Build UserProfile from DB Row
# --------------------------------------------------

def profile_from_row(profile_data) -> UserProfile:
    return UserProfile(
        age=profile_data["age"],
        gender=profile_data["gender"],
        state=profile_data["state"],
        district=profile_data["district"],
        annual_income=profile_data["annual_income"],
        marital_status=profile_data["marital_status"],
        occupation=profile_data["occupation"],
        disability=bool(profile_data["disability"]),
        farmer=bool(profile_data["farmer"]),
        pension=bool(profile_data["pension"]),
        landholding_hectares=float(profile_data["landholding_hectares"]),
        land_acquisition_date=profile_data["land_acquisition_date"],
        land_acquired_by_succession=bool(profile_data["land_acquired_by_succession"]),
        institutional_landholder=bool(profile_data["institutional_landholder"]),
        constitutional_post_holder=bool(profile_data["constitutional_post_holder"]),
        minister_or_legislator=bool(profile_data["minister_or_legislator"]),
        mayor_or_panchayat_chairperson=bool(profile_data["mayor_or_panchayat_chairperson"]),
        government_employee=bool(profile_data["government_employee"]),
        government_employee_group=profile_data["government_employee_group"],
        monthly_pension=profile_data["monthly_pension"],
        income_tax_payer=bool(profile_data["income_tax_payer"]),
        practicing_professional=bool(profile_data["practicing_professional"]),
        nri=bool(profile_data["nri"])
    )


# --------------------------------------------------
# 5. Home
# --------------------------------------------------

@app.get("/", tags=["Health"])
def home():
    return {
        "message": "Welfare AI Backend is running!",
        "version": "1.0.0",
        "docs": "/docs"
    }


# --------------------------------------------------
# 6. Profile API
# --------------------------------------------------

@app.post("/profile", tags=["Profile"])
def create_profile(profile: UserProfile):

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO profiles
    (
        age, gender, state, district, annual_income,
        marital_status, occupation,
        disability, farmer, pension,
        landholding_hectares, land_acquisition_date, land_acquired_by_succession,
        institutional_landholder, constitutional_post_holder,
        minister_or_legislator, mayor_or_panchayat_chairperson,
        government_employee, government_employee_group,
        monthly_pension, income_tax_payer,
        practicing_professional, nri
    )
    VALUES (
        ?, ?, ?, ?, ?, ?, ?,
        ?, ?, ?,
        ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?,
        ?, ?,
        ?, ?
    )
    """, (
        profile.age, profile.gender, profile.state, profile.district,
        profile.annual_income, profile.marital_status, profile.occupation,
        profile.disability, profile.farmer, profile.pension,
        profile.landholding_hectares, profile.land_acquisition_date,
        profile.land_acquired_by_succession,
        profile.institutional_landholder, profile.constitutional_post_holder,
        profile.minister_or_legislator, profile.mayor_or_panchayat_chairperson,
        profile.government_employee, profile.government_employee_group,
        profile.monthly_pension, profile.income_tax_payer,
        profile.practicing_professional, profile.nri
    ))

    profile_id = cursor.lastrowid
    connection.commit()
    connection.close()

    return {
        "profile_id": profile_id,
        "message": "Profile saved successfully"
    }


@app.get("/profiles/{profile_id}", tags=["Profile"])
def get_profile(profile_id: int):
    """Get a saved citizen profile by ID."""

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT * FROM profiles WHERE profile_id = ?
    """, (profile_id,))

    profile_data = cursor.fetchone()
    connection.close()

    if profile_data is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    return dict(profile_data)


# --------------------------------------------------
# 7. Scheme APIs
# --------------------------------------------------

@app.get("/schemes", tags=["Schemes"])
def get_schemes(category: Optional[str] = Query(default=None, description="Filter by category e.g. Agriculture, Education, Health, Housing, Employment, Insurance")):
    """
    List all schemes.
    Optionally filter by category: ?category=Education
    """

    connection = get_db()
    cursor = connection.cursor()

    if category:
        cursor.execute("""
        SELECT * FROM schemes WHERE LOWER(category) = LOWER(?)
        """, (category,))
    else:
        cursor.execute("SELECT * FROM schemes")

    rows = cursor.fetchall()
    connection.close()

    return [dict(row) for row in rows]


@app.get("/schemes/{scheme_id}", tags=["Schemes"])
def get_scheme(scheme_id: str):
    """Get full details of a single scheme."""

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT * FROM schemes WHERE scheme_id = ?
    """, (scheme_id,))

    scheme = cursor.fetchone()

    if scheme is None:
        connection.close()
        raise HTTPException(status_code=404, detail=f"Scheme '{scheme_id}' not found")

    # Also fetch its documents and questions
    cursor.execute("""
    SELECT document_name FROM scheme_documents WHERE scheme_id = ?
    """, (scheme_id,))
    documents = [row["document_name"] for row in cursor.fetchall()]

    cursor.execute("""
    SELECT field, question, answer_type, required
    FROM scheme_questions WHERE scheme_id = ?
    """, (scheme_id,))
    questions = [dict(q) for q in cursor.fetchall()]

    connection.close()

    return {
        **dict(scheme),
        "documents": documents,
        "questions": questions
    }


@app.get("/schemes/{scheme_id}/documents", tags=["Schemes"])
def get_scheme_documents(scheme_id: str):
    """Get the list of documents required for a scheme."""

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT document_name FROM scheme_documents WHERE scheme_id = ?
    """, (scheme_id,))

    rows = cursor.fetchall()
    connection.close()

    return {
        "scheme_id": scheme_id,
        "documents": [row["document_name"] for row in rows]
    }


@app.get("/schemes/{scheme_id}/questions", tags=["Schemes"])
def get_scheme_questions(scheme_id: str):
    """Get scheme-specific questions to ask the citizen."""

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT field, question, answer_type, required
    FROM scheme_questions WHERE scheme_id = ?
    """, (scheme_id,))

    questions = cursor.fetchall()
    connection.close()

    return {
        "scheme_id": scheme_id,
        "questions": [dict(q) for q in questions]
    }


# --------------------------------------------------
# 8. Scheme Answer Helpers
# --------------------------------------------------

def get_scheme_answer(profile_id: int, scheme_id: str, field: str):

    connection = sqlite3.connect(BASE_DIR / "welfare.db")
    cursor = connection.cursor()

    cursor.execute("""
    SELECT value FROM scheme_answers
    WHERE profile_id = ? AND scheme_id = ? AND field = ?
    """, (profile_id, scheme_id, field))

    result = cursor.fetchone()
    connection.close()

    return result[0] if result else None


def convert_answer_value(value):

    if value is None:
        return None

    if isinstance(value, str):

        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False

        try:
            return int(value)
        except ValueError:
            pass

        try:
            return float(value)
        except ValueError:
            pass

    return value


# --------------------------------------------------
# 9. Save Scheme Answers
# --------------------------------------------------

@app.post("/schemes/{scheme_id}/answers", tags=["Scheme Answers"])
def save_scheme_answer(scheme_id: str, answer: SchemeAnswer):
    """Save a single scheme-specific answer for a profile."""

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO scheme_answers (profile_id, scheme_id, field, value)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(profile_id, scheme_id, field)
    DO UPDATE SET value = excluded.value
    """, (answer.profile_id, scheme_id, answer.field, answer.value))

    connection.commit()
    connection.close()

    return {
        "message": "Answer saved successfully",
        "profile_id": answer.profile_id,
        "scheme_id": scheme_id,
        "field": answer.field,
        "value": answer.value
    }


@app.post("/schemes/{scheme_id}/answers/bulk", tags=["Scheme Answers"])
def save_scheme_answers(scheme_id: str, data: SchemeAnswers):
    """Save multiple scheme-specific answers at once."""

    connection = get_db()
    cursor = connection.cursor()

    for field, value in data.answers.items():
        cursor.execute("""
        INSERT INTO scheme_answers (profile_id, scheme_id, field, value)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(profile_id, scheme_id, field)
        DO UPDATE SET value = excluded.value
        """, (data.profile_id, scheme_id, field, value))

    connection.commit()
    connection.close()

    return {
        "message": "All answers saved successfully",
        "profile_id": data.profile_id,
        "scheme_id": scheme_id,
        "answers_saved": len(data.answers)
    }


@app.get("/profiles/{profile_id}/schemes/{scheme_id}/answers", tags=["Scheme Answers"])
def get_scheme_answers(profile_id: int, scheme_id: str):
    """Get all answers a profile has submitted for a scheme."""

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT field, value FROM scheme_answers
    WHERE profile_id = ? AND scheme_id = ?
    """, (profile_id, scheme_id))

    rows = cursor.fetchall()
    connection.close()

    return {
        "profile_id": profile_id,
        "scheme_id": scheme_id,
        "answers": {row["field"]: row["value"] for row in rows}
    }


# --------------------------------------------------
# 10. Missing Questions
# --------------------------------------------------

@app.get("/profiles/{profile_id}/schemes/{scheme_id}/missing-questions", tags=["Eligibility"])
def get_missing_questions(profile_id: int, scheme_id: str):
    """Check which required scheme questions are still unanswered for a profile."""

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT q.field, q.question, q.answer_type, q.required
    FROM scheme_questions q
    LEFT JOIN scheme_answers a
        ON q.scheme_id = a.scheme_id
        AND q.field = a.field
        AND a.profile_id = ?
    WHERE q.scheme_id = ?
    AND q.required = 1
    AND a.field IS NULL
    """, (profile_id, scheme_id))

    rows = cursor.fetchall()
    connection.close()

    return {
        "profile_id": profile_id,
        "scheme_id": scheme_id,
        "missing_count": len(rows),
        "missing_questions": [dict(row) for row in rows]
    }


# --------------------------------------------------
# 11. Eligibility Engine
# --------------------------------------------------

def check_profile_eligibility(
    profile: UserProfile,
    scheme_id: str,
    profile_id: int
):
    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT * FROM eligibility_rules WHERE scheme_id = ?
    """, (scheme_id,))

    rules = cursor.fetchall()
    is_eligible = True
    reasons = []

    # ------------------------------------------
    # PM-KISAN Special: Land Acquisition Cutoff
    # ------------------------------------------
    if scheme_id == "PMKISAN":
        cutoff_date = "2019-02-01"
        if (
            profile.land_acquisition_date > cutoff_date
            and not profile.land_acquired_by_succession
        ):
            is_eligible = False
            reasons.append(
                "Land ownership was acquired after 01-02-2019 and was not "
                "acquired through succession due to death of the landholder"
            )
     # ------------------------------------------
    # PM-JAY Two-Route Logic
    # ------------------------------------------

    pmjay_route_a_indicator = False
    # ------------------------------------------
    # PM-JAY Two-Route Logic
    # ------------------------------------------

    if scheme_id == "PMJAY":

        # --------------------------------------
        # Route 1: Age 70+
        # --------------------------------------

        if profile.age >= 70:

            has_aadhaar = get_scheme_answer(
                profile_id,
                "PMJAY",
                "has_aadhaar"
            )

            if str(has_aadhaar).lower() != "true":

                connection.close()

                return False, [
                    "Aadhaar-based e-KYC is mandatory for enrolment in the "
                    "PM-JAY 70+ senior-citizen route."
                ], []

            connection.close()

            return True, None, [
                "Potentially eligible through the PM-JAY 70+ senior-citizen "
                "route. Final enrolment requires Aadhaar-based e-KYC."
            ]

        # --------------------------------------
        # Route 2: Below 70
        # --------------------------------------

        connection.close()

        return False, [
            "PM-JAY eligibility for applicants below 70 requires verification "
            "against the official PM-JAY beneficiary database / applicable "
            "State beneficiary database. Self-reported profile information "
            "cannot establish final eligibility."
        ], []




    
    # ------------------------------------------
    # Check Every Eligibility Rule
    # ------------------------------------------
    for rule in rules:

        field = rule["field"]
        operator = rule["operator"]
        expected_value = rule["value"]
        rule_type = rule["rule_type"]

        # Is this field a scheme-specific question?
        cursor.execute("""
        SELECT 1 FROM scheme_questions
        WHERE scheme_id = ? AND field = ?
        """, (scheme_id, field))

        is_scheme_question = cursor.fetchone()

        if is_scheme_question:
            actual_value = get_scheme_answer(profile_id, scheme_id, field)
        elif hasattr(profile, field):
            actual_value = getattr(profile, field)
        else:
            actual_value = None
                    # PM-KISAN exception:
        # MTS / Class IV / Group D government employees are NOT excluded.
        if (
            scheme_id == "PMKISAN"
            and field == "government_employee"
            and str(getattr(profile, "government_employee_group", "")).strip().lower()
                in {"mts", "class iv", "group d"}
        ):
            continue

        if actual_value is None:
            is_eligible = False
            reasons.append(f"Required information missing: {field}")
            continue

        actual_value = convert_answer_value(actual_value)

        # Type-match expected_value to actual_value
        if isinstance(actual_value, bool):
            expected_value = (expected_value.lower() == "true")
        elif isinstance(actual_value, int):
            expected_value = int(expected_value)
        elif isinstance(actual_value, float):
            expected_value = float(expected_value)

        # Inclusion rule: condition must be TRUE to pass
        if rule_type == "inclusion":
            failed = False
            if operator == "==" and actual_value != expected_value:
                failed = True
            elif operator == ">=" and actual_value < expected_value:
                failed = True
            elif operator == "<=" and actual_value > expected_value:
                failed = True
            elif operator == ">" and actual_value <= expected_value:
                failed = True
            elif operator == "<" and actual_value >= expected_value:
                failed = True
            elif operator == "!=" and actual_value == expected_value:
                failed = True

            if failed:
                is_eligible = False
                reasons.append(rule["reason"])

        # Exclusion rule: condition must be FALSE to pass
        elif rule_type == "exclusion":
            failed = False
            if operator == "==" and actual_value == expected_value:
                failed = True
            elif operator == ">=" and actual_value >= expected_value:
                failed = True
            elif operator == "<=" and actual_value <= expected_value:
                failed = True
            elif operator == ">" and actual_value > expected_value:
                failed = True
            elif operator == "<" and actual_value < expected_value:
                failed = True
            elif operator == "!=" and actual_value != expected_value:
                failed = True

            if failed:
                is_eligible = False
                reasons.append(rule["reason"])

       # ------------------------------------------
    # PM-JAY Route B final handling
    # ------------------------------------------

    if (
        scheme_id == "PMJAY"
        and profile.age < 70
        and not pmjay_route_a_indicator
    ):

        connection.close()

        return False, reasons, reasons


    connection.close()


    if is_eligible:

        return True, None, reasons


    return False, reasons, reasons


# --------------------------------------------------
# 12. General Eligibility API (all schemes)
# --------------------------------------------------

@app.post("/eligibility", tags=["Eligibility"])
def check_eligibility(profile: UserProfile):
    """
    Check a profile against ALL schemes.
    Returns eligible_schemes and not_eligible_schemes.
    Note: Uses profile_id=0 so scheme-specific question answers
    are not considered. Use /profiles/{id}/schemes/{id}/eligibility
    for full per-profile checks.
    """

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM schemes")
    schemes = cursor.fetchall()

    eligible_schemes = []
    not_eligible_schemes = []

    for scheme in schemes:

        is_eligible, reason, reasons = check_profile_eligibility(
            profile, scheme["scheme_id"], 0
        )

        if is_eligible:
            cursor.execute("""
            SELECT document_name FROM scheme_documents WHERE scheme_id = ?
            """, (scheme["scheme_id"],))

            documents = [row["document_name"] for row in cursor.fetchall()]

            eligible_schemes.append({
                "scheme_id": scheme["scheme_id"],
                "name": scheme["name"],
                "category": scheme["category"],
                "description": scheme["description"],
                "status": "potentially_eligible",
                "reasons": reasons,
                "documents": documents
            })
        else:
            not_eligible_schemes.append({
                "scheme_id": scheme["scheme_id"],
                "name": scheme["name"],
                "category": scheme["category"],
                "reasons": reason
            })

    connection.close()

    return {
        "eligible_count": len(eligible_schemes),
        "not_eligible_count": len(not_eligible_schemes),
        "eligible_schemes": eligible_schemes,
        "not_eligible_schemes": not_eligible_schemes
    }


# --------------------------------------------------
# 13. Scheme-Specific Eligibility API (saved profile)
# --------------------------------------------------

@app.post(
    "/profiles/{profile_id}/schemes/{scheme_id}/eligibility",
    tags=["Eligibility"]
)
def check_scheme_eligibility(profile_id: int, scheme_id: str):
    """
    Check eligibility of a saved profile for one specific scheme.
    Also checks for missing required answers first.
    """

    connection = get_db()
    cursor = connection.cursor()

    # Step 0: Check for missing required answers
    cursor.execute("""
    SELECT q.field, q.question, q.answer_type, q.required
    FROM scheme_questions q
    LEFT JOIN scheme_answers a
        ON q.scheme_id = a.scheme_id
        AND q.field = a.field
        AND a.profile_id = ?
    WHERE q.scheme_id = ?
    AND q.required = 1
    AND a.field IS NULL
    """, (profile_id, scheme_id))

    missing_questions = cursor.fetchall()

    if missing_questions:
        connection.close()
        return {
            "profile_id": profile_id,
            "scheme_id": scheme_id,
            "status": "information_required",
            "missing_count": len(missing_questions),
            "missing_questions": [dict(q) for q in missing_questions]
        }

    # Step 1: Get profile
    cursor.execute("""
    SELECT * FROM profiles WHERE profile_id = ?
    """, (profile_id,))

    profile_data = cursor.fetchone()

    if profile_data is None:
        connection.close()
        raise HTTPException(status_code=404, detail="Profile not found")

    # Step 2: Get scheme
    cursor.execute("""
    SELECT * FROM schemes WHERE scheme_id = ?
    """, (scheme_id,))

    scheme = cursor.fetchone()

    if scheme is None:
        connection.close()
        raise HTTPException(status_code=404, detail=f"Scheme '{scheme_id}' not found")

    # Step 3: Build profile object
    profile = profile_from_row(profile_data)

    # Step 4: Run eligibility check
    is_eligible, reason, reasons = check_profile_eligibility(
        profile, scheme_id, profile_id
    )

    # Step 5: Get required documents
    cursor.execute("""
    SELECT document_name FROM scheme_documents WHERE scheme_id = ?
    """, (scheme_id,))

    documents = [row["document_name"] for row in cursor.fetchall()]

    connection.close()

    if is_eligible:
        return {
            "profile_id": profile_id,
            "scheme_id": scheme_id,
            "scheme_name": scheme["name"],
            "status": "potentially_eligible",
            "reasons": reasons,
            "documents": documents
        }

    return {
        "profile_id": profile_id,
        "scheme_id": scheme_id,
        "scheme_name": scheme["name"],
        "status": "not_eligible",
        "reasons": reasons,
        "documents": documents
    }


# --------------------------------------------------
# 14. Bulk Eligibility for a Saved Profile
#     (check one profile against ALL schemes)
# --------------------------------------------------

@app.post("/profiles/{profile_id}/eligibility", tags=["Eligibility"])
def check_profile_all_schemes(
    profile_id: int,
    category: Optional[str] = Query(default=None, description="Filter by scheme category")
):
    """
    Check a saved profile against all schemes (or a category).
    Considers scheme-specific answers already stored for this profile.
    """

    connection = get_db()
    cursor = connection.cursor()

    # Get profile
    cursor.execute("SELECT * FROM profiles WHERE profile_id = ?", (profile_id,))
    profile_data = cursor.fetchone()

    if profile_data is None:
        connection.close()
        raise HTTPException(status_code=404, detail="Profile not found")

    profile = profile_from_row(profile_data)

    # Get schemes (optionally filtered)
    if category:
        cursor.execute("SELECT * FROM schemes WHERE LOWER(category) = LOWER(?)", (category,))
    else:
        cursor.execute("SELECT * FROM schemes")

    schemes = cursor.fetchall()
    connection.close()

    eligible_schemes = []
    not_eligible_schemes = []
    information_required_schemes = []

    for scheme in schemes:

        scheme_id = scheme["scheme_id"]

        # Check for missing answers
        conn2 = get_db()
        cur2 = conn2.cursor()
        cur2.execute("""
        SELECT q.field, q.question, q.answer_type, q.required
        FROM scheme_questions q
        LEFT JOIN scheme_answers a
            ON q.scheme_id = a.scheme_id
            AND q.field = a.field
            AND a.profile_id = ?
        WHERE q.scheme_id = ?
        AND q.required = 1
        AND a.field IS NULL
        """, (profile_id, scheme_id))

        missing = cur2.fetchall()
        conn2.close()

        if missing:
            information_required_schemes.append({
                "scheme_id": scheme_id,
                "name": scheme["name"],
                "category": scheme["category"],
                "status": "information_required",
                "missing_questions": [dict(q) for q in missing]
            })
            continue

        is_eligible, reason, reasons = check_profile_eligibility(
            profile, scheme_id, profile_id
        )

        if is_eligible:
            eligible_schemes.append({
                "scheme_id": scheme_id,
                "name": scheme["name"],
                "category": scheme["category"],
                "status": "potentially_eligible"
            })
        else:
            not_eligible_schemes.append({
                "scheme_id": scheme_id,
                "name": scheme["name"],
                "category": scheme["category"],
                "status": "not_eligible",
                "reasons": reason
            })

    return {
        "profile_id": profile_id,
        "eligible_count": len(eligible_schemes),
        "not_eligible_count": len(not_eligible_schemes),
        "information_required_count": len(information_required_schemes),
        "eligible_schemes": eligible_schemes,
        "not_eligible_schemes": not_eligible_schemes,
        "information_required_schemes": information_required_schemes
    }


# --------------------------------------------------
# 15. Applications
# --------------------------------------------------

@app.post("/applications", tags=["Applications"])
def create_application(application: Application):
    """Create a new application after verifying eligibility."""

    connection = get_db()
    cursor = connection.cursor()

    # Check profile exists
    cursor.execute("SELECT * FROM profiles WHERE profile_id = ?", (application.profile_id,))
    profile_data = cursor.fetchone()

    if profile_data is None:
        connection.close()
        raise HTTPException(status_code=404, detail="Profile not found")

    # Check scheme exists
    cursor.execute("SELECT * FROM schemes WHERE scheme_id = ?", (application.scheme_id,))
    scheme = cursor.fetchone()

    if scheme is None:
        connection.close()
        raise HTTPException(status_code=404, detail=f"Scheme '{application.scheme_id}' not found")

    # Build profile object and run eligibility
    profile = profile_from_row(profile_data)

    is_eligible, reason, reasons = check_profile_eligibility(
        profile, application.scheme_id, application.profile_id
    )

    if not is_eligible:
        connection.close()
        return {
            "message": "Application cannot be created — profile is not eligible",
            "scheme_id": application.scheme_id,
            "reasons": reason
        }

    # Create application
    cursor.execute("""
    INSERT INTO applications
    (
        profile_id, scheme_id, applicant_name,
        age, gender, state, district, annual_income,
        marital_status, occupation, status
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        application.profile_id,
        application.scheme_id,
        application.applicant_name,
        profile_data["age"],
        profile_data["gender"],
        profile_data["state"],
        profile_data["district"],
        profile_data["annual_income"],
        profile_data["marital_status"],
        profile_data["occupation"],
        "draft"
    ))

    application_id = cursor.lastrowid
    connection.commit()
    connection.close()

    return {
        "application_id": application_id,
        "profile_id": application.profile_id,
        "scheme_id": application.scheme_id,
        "applicant_name": application.applicant_name,
        "status": "draft",
        "message": "Application created successfully"
    }


@app.get("/applications", tags=["Applications"])
def get_applications(
    profile_id: Optional[int] = Query(default=None, description="Filter by profile ID"),
    status: Optional[str] = Query(default=None, description="Filter by status e.g. draft, submitted")
):
    """List all applications. Optionally filter by profile_id or status."""

    connection = get_db()
    cursor = connection.cursor()

    query = "SELECT * FROM applications WHERE 1=1"
    params = []

    if profile_id is not None:
        query += " AND profile_id = ?"
        params.append(profile_id)

    if status is not None:
        query += " AND status = ?"
        params.append(status)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    connection.close()

    return {
        "count": len(rows),
        "applications": [dict(row) for row in rows]
    }


@app.get("/applications/{application_id}", tags=["Applications"])
def get_application(application_id: int):
    """Get a single application by ID."""

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT * FROM applications WHERE application_id = ?
    """, (application_id,))

    application = cursor.fetchone()
    connection.close()

    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")

    return dict(application)


@app.put("/applications/{application_id}/status", tags=["Applications"])
def update_application_status(application_id: int, status: str):
    """Update the status of an application."""

    if status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Invalid application status",
                "allowed_statuses": VALID_STATUSES
            }
        )

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
    UPDATE applications SET status = ? WHERE application_id = ?
    """, (status, application_id))

    connection.commit()

    if cursor.rowcount == 0:
        connection.close()
        raise HTTPException(status_code=404, detail="Application not found")

    connection.close()

    return {
        "application_id": application_id,
        "status": status,
        "message": "Application status updated successfully"
    }


# --------------------------------------------------
# 16. Application Documents
# --------------------------------------------------

@app.post("/applications/{application_id}/documents", tags=["Documents"])
def add_application_document(application_id: int, document: ApplicationDocument):
    """Add a document record (by name) to an application. Use /upload for actual files."""

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT application_id FROM applications WHERE application_id = ?
    """, (application_id,))

    if cursor.fetchone() is None:
        connection.close()
        raise HTTPException(status_code=404, detail="Application not found")

    cursor.execute("""
    INSERT INTO application_documents (application_id, document_name, document_status)
    VALUES (?, ?, ?)
    """, (application_id, document.document_name, "submitted"))

    document_id = cursor.lastrowid
    connection.commit()
    connection.close()

    return {
        "document_id": document_id,
        "application_id": application_id,
        "document_name": document.document_name,
        "document_status": "submitted",
        "message": "Document record added successfully"
    }


@app.get("/applications/{application_id}/documents", tags=["Documents"])
def get_application_documents(application_id: int):
    """Get all documents attached to an application."""

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT application_id FROM applications WHERE application_id = ?
    """, (application_id,))

    if cursor.fetchone() is None:
        connection.close()
        raise HTTPException(status_code=404, detail="Application not found")

    cursor.execute("""
    SELECT document_id, document_name, document_status
    FROM application_documents
    WHERE application_id = ?
    """, (application_id,))

    rows = cursor.fetchall()
    connection.close()

    return {
        "application_id": application_id,
        "document_count": len(rows),
        "documents": [dict(row) for row in rows]
    }


@app.post("/applications/{application_id}/documents/upload", tags=["Documents"])
async def upload_document(
    application_id: int,
    file: UploadFile = File(...)
):
    """
    Upload an actual file (PDF, JPG, JPEG, PNG) for an application.
    Max size: 5 MB.
    """

    # 1. Check application exists
    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT application_id FROM applications WHERE application_id = ?
    """, (application_id,))

    if cursor.fetchone() is None:
        connection.close()
        raise HTTPException(status_code=404, detail="Application not found")

    # 2. Validate extension
    allowed_extensions = {".pdf", ".jpg", ".jpeg", ".png"}
    original_filename = file.filename or ""
    file_extension = Path(original_filename).suffix.lower()

    if file_extension not in allowed_extensions:
        connection.close()
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Unsupported file type",
                "allowed_types": list(allowed_extensions)
            }
        )

    # 3. Read and validate size
    contents = await file.read()
    file_size = len(contents)
    max_size = 5 * 1024 * 1024  # 5 MB

    if file_size > max_size:
        connection.close()
        raise HTTPException(
            status_code=400,
            detail=f"File size {file_size} bytes exceeds the 5 MB limit."
        )

    # 4. Create safe filename (prevent path traversal)
    stem = Path(original_filename).stem[:50]
    safe_stem = "".join(c for c in stem if c.isalnum() or c in "-_")
    safe_filename = f"{application_id}_{safe_stem}{file_extension}"

    # 5. Save file
    upload_folder = BASE_DIR / "uploads"
    upload_folder.mkdir(exist_ok=True)

    with open(upload_folder / safe_filename, "wb") as f:
        f.write(contents)

    # 6. Save DB record
    cursor.execute("""
    INSERT INTO application_documents (application_id, document_name, document_status)
    VALUES (?, ?, ?)
    """, (application_id, safe_filename, "uploaded"))

    document_id = cursor.lastrowid
    connection.commit()
    connection.close()

    return {
        "document_id": document_id,
        "application_id": application_id,
        "original_filename": original_filename,
        "stored_filename": safe_filename,
        "file_size_bytes": file_size,
        "document_status": "uploaded",
        "message": "File uploaded successfully"
    }


@app.delete("/applications/{application_id}/documents/{document_id}", tags=["Documents"])
def delete_application_document(application_id: int, document_id: int):
    """Delete a document record (and its file if it exists) from an application."""

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT document_name, document_status
    FROM application_documents
    WHERE document_id = ? AND application_id = ?
    """, (document_id, application_id))

    doc = cursor.fetchone()

    if doc is None:
        connection.close()
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete the actual file if it was an upload
    if doc["document_status"] == "uploaded":
        file_path = BASE_DIR / "uploads" / doc["document_name"]
        if file_path.exists():
            file_path.unlink()

    cursor.execute("""
    DELETE FROM application_documents WHERE document_id = ?
    """, (document_id,))

    connection.commit()
    connection.close()

    return {
        "document_id": document_id,
        "message": "Document deleted successfully"
    }
