"""
setup_db.py
------------
Run this ONCE to create all tables and seed scheme data.

    python setup_db.py

Re-running is safe — uses INSERT OR IGNORE / DELETE + INSERT pattern.
"""

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def setup():

    connection = sqlite3.connect(BASE_DIR / "welfare.db")
    cursor = connection.cursor()

    # ==================================================
    # TABLE: profiles
    # ==================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        profile_id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        age                             INTEGER,
        gender                          TEXT,
        state                           TEXT,
        district                        TEXT,
        annual_income                   INTEGER,
        marital_status                  TEXT,
        occupation                      TEXT,
        disability                      BOOLEAN,
        farmer                          BOOLEAN,
        pension                         BOOLEAN,
        landholding_hectares            REAL,
        land_acquisition_date           TEXT,
        land_acquired_by_succession     BOOLEAN,
        institutional_landholder        BOOLEAN,
        constitutional_post_holder      BOOLEAN,
        minister_or_legislator          BOOLEAN,
        mayor_or_panchayat_chairperson  BOOLEAN,
        government_employee             BOOLEAN,
        government_employee_group       TEXT,
        monthly_pension                 INTEGER,
        income_tax_payer                BOOLEAN,
        practicing_professional         BOOLEAN,
        nri                             BOOLEAN
    )
    """)

    # ==================================================
    # TABLE: schemes
    # ==================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS schemes (
        scheme_id       TEXT PRIMARY KEY,
        name            TEXT,
        description     TEXT,
        state           TEXT,
        category        TEXT,
        min_age         INTEGER,
        max_age         INTEGER,
        max_income      INTEGER,
        marital_status  TEXT
    )
    """)

    # ==================================================
    # TABLE: eligibility_rules
    # ==================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS eligibility_rules (
        rule_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        scheme_id   TEXT,
        field       TEXT,
        operator    TEXT,
        value       TEXT,
        rule_type   TEXT,
        reason      TEXT
    )
    """)

    # ==================================================
    # TABLE: scheme_questions
    # ==================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scheme_questions (
        question_id INTEGER PRIMARY KEY AUTOINCREMENT,
        scheme_id   TEXT,
        field       TEXT,
        question    TEXT,
        answer_type TEXT,
        required    INTEGER DEFAULT 1
    )
    """)

    # ==================================================
    # TABLE: scheme_answers
    # ==================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scheme_answers (
        answer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id  INTEGER,
        scheme_id   TEXT,
        field       TEXT,
        value       TEXT,
        UNIQUE(profile_id, scheme_id, field)
    )
    """)

    # ==================================================
    # TABLE: scheme_documents
    # ==================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scheme_documents (
        doc_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        scheme_id       TEXT,
        document_name   TEXT
    )
    """)

    # ==================================================
    # TABLE: applications
    # ==================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS applications (
        application_id  INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id      INTEGER,
        scheme_id       TEXT,
        applicant_name  TEXT,
        age             INTEGER,
        gender          TEXT,
        state           TEXT,
        district        TEXT,
        annual_income   INTEGER,
        marital_status  TEXT,
        occupation      TEXT,
        status          TEXT DEFAULT 'draft'
    )
    """)

    # ==================================================
    # TABLE: application_documents
    # ==================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS application_documents (
        document_id         INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id      INTEGER,
        document_name       TEXT,
        document_status     TEXT DEFAULT 'pending'
    )
    """)

    # ==================================================
    # TABLE: document_verifications  (for OCR module)
    # ==================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS document_verifications (
        verification_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id         INTEGER UNIQUE,
        application_id      INTEGER,
        document_type       TEXT,
        extracted_fields    TEXT,
        verification_status TEXT DEFAULT 'pending',
        mismatch_fields     TEXT,
        verified_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (document_id) REFERENCES application_documents(document_id)
    )
    """)

    print("✅ All tables created.")


    # ==================================================
    # ██████████████████████████████████████████████████
    #  SCHEME DATA
    # ██████████████████████████████████████████████████
    # ==================================================


    # --------------------------------------------------
    # 1. PM-KISAN
    # --------------------------------------------------
    cursor.execute("""
    INSERT OR IGNORE INTO schemes
        (scheme_id, name, description, state, category, min_age, max_age, max_income, marital_status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("PMKISAN", "PM-KISAN",
          "Direct income support of ₹6,000/year in 3 instalments to eligible farmer families.",
          "ALL", "Agriculture", None, None, None, None))

    cursor.execute("DELETE FROM eligibility_rules WHERE scheme_id = 'PMKISAN'")
    for field, operator, value, rule_type, reason in [
        ("farmer",                      "==", "true",   "inclusion",  "Applicant must be a farmer (landholder)"),
        ("institutional_landholder",    "==", "true",   "exclusion",  "Institutional landholders are excluded"),
        ("constitutional_post_holder",  "==", "true",   "exclusion",  "Constitutional post holders are excluded"),
        ("minister_or_legislator",      "==", "true",   "exclusion",  "Former or current ministers/legislators are excluded"),
        ("mayor_or_panchayat_chairperson", "==", "true","exclusion",  "Mayors and panchayat chairpersons are excluded"),
        ("government_employee",         "==", "true",   "exclusion",  "Serving government employees are excluded (Multi-Tasking Staff / Class IV / Group D employees are exempt)"),
        ("monthly_pension",             ">=", "10000",  "exclusion",  "Pensioners with ₹10,000+ monthly pension are excluded"),
        ("income_tax_payer",            "==", "true",   "exclusion",  "Income tax payers are excluded"),
        ("practicing_professional",     "==", "true",   "exclusion",  "Registered professional practitioners (doctors, engineers, lawyers, CA, architects) are excluded"),
        ("nri",                         "==", "true",   "exclusion",  "NRIs are excluded"),
    ]:
        cursor.execute("INSERT INTO eligibility_rules (scheme_id,field,operator,value,rule_type,reason) VALUES (?,?,?,?,?,?)",
                       ("PMKISAN", field, operator, value, rule_type, reason))

    cursor.execute("DELETE FROM scheme_documents WHERE scheme_id = 'PMKISAN'")
    for doc in ["Land ownership / cultivable land proof", "Aadhaar Card",
                "Bank account details", "Mobile number linked to Aadhaar",
                "Self-declaration form", "PM-KISAN eKYC"]:
        cursor.execute("INSERT INTO scheme_documents (scheme_id, document_name) VALUES (?,?)", ("PMKISAN", doc))

    print("✅ PM-KISAN seeded.")

    # --------------------------------------------------
    # 2. PM-USP / CSSS Scholarship
    # --------------------------------------------------

    cursor.execute("""
    INSERT OR IGNORE INTO schemes
        (scheme_id, name, description, state, category,
         min_age, max_age, max_income, marital_status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "PMUSP",
        "Central Sector Scheme of Scholarships (CSSS)",
        "Merit-cum-means scholarship for eligible students pursuing regular higher education.",
        "ALL",
        "Education",
        None,
        None,
        450000,
        None
    ))

    # --------------------------------------------------
    # PM-USP CSSS Eligibility Rules
    # Fresh-application conditions
    # --------------------------------------------------

    cursor.execute("""
    DELETE FROM eligibility_rules
    WHERE scheme_id = 'PMUSP'
    """)

    pm_usp_rules = [

        (
            "class_12_percentile",
            ">",
            "80",
            "inclusion",
            "Applicant must be above the 80th percentile of successful Class 12 candidates in the relevant stream."
        ),

        (
            "regular_course",
            "==",
            "true",
            "inclusion",
            "Applicant must be pursuing a regular degree course."
        ),

        (
            "institution_recognized",
            "==",
            "true",
            "inclusion",
            "Applicant must be studying in a recognized college/institution."
        ),

        (
            "annual_income",
            "<=",
            "450000",
            "inclusion",
            "Gross parental/family income must not exceed ₹4.5 lakh per annum."
        ),

        (
            "receiving_other_scholarship",
            "==",
            "false",
            "inclusion",
            "Applicant must not be receiving another scholarship, fee waiver or reimbursement."
        ),

        (
            "distance_or_correspondence",
            "==",
            "false",
            "inclusion",
            "Applicant must not be pursuing the course through correspondence or distance mode."
        ),

        (
            "diploma_course",
            "==",
            "false",
            "inclusion",
            "Diploma students are not eligible."
        ),

        (
            "drop_after_12th",
            "==",
            "false",
            "inclusion",
            "Students who took a drop after Class 12 are not eligible for a fresh application."
        )
    ]

    for field, operator, value, rule_type, reason in pm_usp_rules:
        cursor.execute("""
        INSERT INTO eligibility_rules
        (scheme_id, field, operator, value, rule_type, reason)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "PMUSP",
            field,
            operator,
            value,
            rule_type,
            reason
        ))

    # --------------------------------------------------
    # PM-USP CSSS Questions
    # --------------------------------------------------

    cursor.execute("""
    DELETE FROM scheme_questions
    WHERE scheme_id = 'PMUSP'
    """)

    pm_usp_questions = [

        (
            "class_12_percentile",
            "What was your Class 12 percentile?",
            "number",
            1
        ),

        (
            "regular_course",
            "Are you pursuing a regular degree course?",
            "boolean",
            1
        ),

        (
            "institution_recognized",
            "Is your college/institution recognized by the relevant regulatory body?",
            "boolean",
            1
        ),

        (
            "receiving_other_scholarship",
            "Are you receiving any other scholarship, fee waiver or reimbursement?",
            "boolean",
            1
        ),

        (
            "distance_or_correspondence",
            "Are you pursuing the course through distance or correspondence mode?",
            "boolean",
            1
        ),

        (
            "diploma_course",
            "Are you pursuing a diploma course?",
            "boolean",
            1
        ),

        (
            "drop_after_12th",
            "Did you take a drop after Class 12?",
            "boolean",
            1
        )
    ]

    for field, question, answer_type, required in pm_usp_questions:
        cursor.execute("""
        INSERT INTO scheme_questions
        (scheme_id, field, question, answer_type, required)
        VALUES (?, ?, ?, ?, ?)
        """, (
            "PMUSP",
            field,
            question,
            answer_type,
            required
        ))

    # --------------------------------------------------
    # PM-USP Documents
    # --------------------------------------------------

    cursor.execute("""
    DELETE FROM scheme_documents
    WHERE scheme_id = 'PMUSP'
    """)

    for doc in [
        "Class 12 Mark Sheet",
        "Family Income Certificate",
        "Category / Caste Certificate (if applicable)",
        "Disability Certificate (if applicable)"
    ]:
        cursor.execute("""
        INSERT INTO scheme_documents
        (scheme_id, document_name)
        VALUES (?, ?)
        """, (
            "PMUSP",
            doc
        ))

    print("✅ CSSS/PM-USP scholarship seeded.")
    



    # --------------------------------------------------
    # 3. Ayushman Bharat PM-JAY  (official 2026 document)
    #
    #  TWO ROUTES:
    #  Route A — Age 70+  : eligible regardless of income/assets
    #  Route B — Age < 70 : depends on SECC beneficiary database
    #                        (we flag as beneficiary_database_verification_required)
    #
    #  The eligibility engine returns "potentially_eligible" when age >= 70.
    #  For age < 70 the scheme-question answers are used to determine
    #  whether the profile matches any SECC rural/urban category,
    #  and the final status is returned as a special note in reasons[].
    #
    #  Exclusions (SECC-derived asset filters) apply ONLY to Route B.
    #  A 70+ person is NOT subject to asset/income exclusions.
    # --------------------------------------------------
        # --------------------------------------------------
    # 3. Ayushman Bharat PM-JAY
    # --------------------------------------------------

    cursor.execute("""
    INSERT OR IGNORE INTO schemes
        (scheme_id, name, description, state, category,
         min_age, max_age, max_income, marital_status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "PMJAY",
        "Ayushman Bharat PM-JAY",
        "Government-funded health assurance scheme. For citizens aged 70 years or above, eligibility is based on age irrespective of economic status. For citizens below 70, eligibility depends on the official PM-JAY beneficiary database / applicable state beneficiary database.",
        "ALL",
        "Health",
        None,
        None,
        None,
        None
    ))

    # --------------------------------------------------
    # PM-JAY
    # Do NOT attempt to recreate the full SECC database
    # eligibility using self-reported profile fields.
    # --------------------------------------------------

    cursor.execute("""
    DELETE FROM eligibility_rules
    WHERE scheme_id = 'PMJAY'
    """)

    # --------------------------------------------------
    # PM-JAY Questions
    # --------------------------------------------------

    cursor.execute("""
    DELETE FROM scheme_questions
    WHERE scheme_id = 'PMJAY'
    """)

    pmjay_questions = [

        (
            "has_aadhaar",
            "Do you have an Aadhaar card?",
            "boolean",
            0
        ),

        (
            "official_beneficiary_database_verified",
            "Has your PM-JAY beneficiary status been verified in the official beneficiary/state database?",
            "boolean",
            0
        )
    ]

    for field, question, answer_type, required in pmjay_questions:
        cursor.execute("""
        INSERT INTO scheme_questions
        (scheme_id, field, question, answer_type, required)
        VALUES (?, ?, ?, ?, ?)
        """, (
            "PMJAY",
            field,
            question,
            answer_type,
            required
        ))

    # --------------------------------------------------
    # PM-JAY Documents
    # --------------------------------------------------

    cursor.execute("""
    DELETE FROM scheme_documents
    WHERE scheme_id = 'PMJAY'
    """)

    for doc in [
        "Aadhaar Card (mandatory for 70+ e-KYC enrolment)",
        "PM-JAY / State Beneficiary Database Verification (below 70)",
        "Ration Card / Family ID (if applicable for beneficiary identification)",
        "Government Photo ID (if applicable)",
        "Proof of relationship for family members (if applicable)"
    ]:
        cursor.execute("""
        INSERT INTO scheme_documents
        (scheme_id, document_name)
        VALUES (?, ?)
        """, (
            "PMJAY",
            doc
        ))

    print("✅ PM-JAY seeded.")




     
       



    # --------------------------------------------------
    # 4. PM Awas Yojana - Gramin (PMAY-G)
    # --------------------------------------------------
    cursor.execute("""
    INSERT OR IGNORE INTO schemes
        (scheme_id, name, description, state, category, min_age, max_age, max_income, marital_status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("PMAYG", "PM Awas Yojana - Gramin",
          "Financial assistance for rural homeless / kutcha-house families to build a pucca house.",
          "ALL", "Housing", 18, None, None, None))

    cursor.execute("DELETE FROM eligibility_rules WHERE scheme_id = 'PMAYG'")
    for field, operator, value, rule_type, reason in [
        ("institutional_landholder", "==", "true", "exclusion", "Institutional landholders are excluded"),
        ("government_employee",      "==", "true", "exclusion", "Government employees are excluded"),
        ("income_tax_payer",         "==", "true", "exclusion", "Income-tax payers are excluded"),
        ("monthly_pension",          ">=", "10000","exclusion", "Pensioners receiving ₹10,000+ monthly are excluded"),
    ]:
        cursor.execute("INSERT INTO eligibility_rules (scheme_id,field,operator,value,rule_type,reason) VALUES (?,?,?,?,?,?)",
                       ("PMAYG", field, operator, value, rule_type, reason))

    cursor.execute("DELETE FROM scheme_questions WHERE scheme_id = 'PMAYG'")
    for field, question, answer_type, required in [
        ("house_ownership",  "Do you currently own a pucca (permanent concrete) house?",           "boolean", 1),
        ("secc_listed",      "Is your family listed in the SECC 2011 data?",                       "boolean", 1),
        ("bpl_card",         "Do you hold a BPL (Below Poverty Line) ration card?",                "boolean", 1),
        ("rural_area",       "Are you residing in a rural / gram panchayat area?",                 "boolean", 1),
    ]:
        cursor.execute("INSERT INTO scheme_questions (scheme_id,field,question,answer_type,required) VALUES (?,?,?,?,?)",
                       ("PMAYG", field, question, answer_type, required))

    cursor.execute("DELETE FROM scheme_documents WHERE scheme_id = 'PMAYG'")
    for doc in ["Aadhaar Card", "BPL Ration Card / SECC data proof",
                "Bank passbook (first page)", "Mobile number linked to Aadhaar",
                "Passport-size photograph", "Self-declaration of houselessness"]:
        cursor.execute("INSERT INTO scheme_documents (scheme_id, document_name) VALUES (?,?)", ("PMAYG", doc))

    print("✅ PMAY-G seeded.")


    # --------------------------------------------------
    # 5. MGNREGS / NREGA
    # --------------------------------------------------
    cursor.execute("""
    INSERT OR IGNORE INTO schemes
        (scheme_id, name, description, state, category, min_age, max_age, max_income, marital_status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("NREGA", "Mahatma Gandhi NREGS",
          "Guarantees 100 days of unskilled wage employment per year to rural households.",
          "ALL", "Employment", 18, None, None, None))

    cursor.execute("DELETE FROM eligibility_rules WHERE scheme_id = 'NREGA'")
    for field, operator, value, rule_type, reason in [
        ("age", ">=", "18", "inclusion", "Applicant must be 18 years or older"),
    ]:
        cursor.execute("INSERT INTO eligibility_rules (scheme_id,field,operator,value,rule_type,reason) VALUES (?,?,?,?,?,?)",
                       ("NREGA", field, operator, value, rule_type, reason))

    cursor.execute("DELETE FROM scheme_questions WHERE scheme_id = 'NREGA'")
    for field, question, answer_type, required in [
        ("rural_area",          "Are you residing in a rural / gram panchayat area?",          "boolean", 1),
        ("willing_unskilled",   "Are you willing to do unskilled manual work?",                "boolean", 1),
        ("job_card_holder",     "Do you currently hold a NREGA Job Card?",                     "boolean", 0),
    ]:
        cursor.execute("INSERT INTO scheme_questions (scheme_id,field,question,answer_type,required) VALUES (?,?,?,?,?)",
                       ("NREGA", field, question, answer_type, required))

    cursor.execute("DELETE FROM scheme_documents WHERE scheme_id = 'NREGA'")
    for doc in ["Aadhaar Card", "Passport-size photograph",
                "Bank passbook / Jan Dhan account details",
                "Age proof (Birth Certificate / School certificate)"]:
        cursor.execute("INSERT INTO scheme_documents (scheme_id, document_name) VALUES (?,?)", ("NREGA", doc))

    print("✅ MGNREGS/NREGA seeded.")


    # --------------------------------------------------
    # 6. PM Suraksha Bima Yojana (PMSBY)
    # --------------------------------------------------
    cursor.execute("""
    INSERT OR IGNORE INTO schemes
        (scheme_id, name, description, state, category, min_age, max_age, max_income, marital_status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("PMSBY", "PM Suraksha Bima Yojana",
          "Accidental death and disability insurance cover of ₹2 lakh at ₹20/year premium.",
          "ALL", "Insurance", 18, 70, None, None))

    cursor.execute("DELETE FROM eligibility_rules WHERE scheme_id = 'PMSBY'")
    for field, operator, value, rule_type, reason in [
        ("age", ">=", "18", "inclusion", "Applicant must be at least 18 years old"),
        ("age", "<=", "70", "inclusion", "Applicant must be 70 years or younger"),
        ("nri",  "==", "true", "exclusion", "NRI applicants are excluded"),
    ]:
        cursor.execute("INSERT INTO eligibility_rules (scheme_id,field,operator,value,rule_type,reason) VALUES (?,?,?,?,?,?)",
                       ("PMSBY", field, operator, value, rule_type, reason))

    cursor.execute("DELETE FROM scheme_questions WHERE scheme_id = 'PMSBY'")
    for field, question, answer_type, required in [
        ("has_bank_account",        "Do you have a savings bank or post office account?",    "boolean", 1),
        ("aadhaar_linked_bank",     "Is your Aadhaar linked to your bank account?",          "boolean", 1),
    ]:
        cursor.execute("INSERT INTO scheme_questions (scheme_id,field,question,answer_type,required) VALUES (?,?,?,?,?)",
                       ("PMSBY", field, question, answer_type, required))

    cursor.execute("DELETE FROM scheme_documents WHERE scheme_id = 'PMSBY'")
    for doc in ["Aadhaar Card", "Bank account details / passbook", "Mobile number"]:
        cursor.execute("INSERT INTO scheme_documents (scheme_id, document_name) VALUES (?,?)", ("PMSBY", doc))

    print("✅ PMSBY seeded.")


    # --------------------------------------------------
    # 7. NSP OBC Pre-Matric Scholarship
    # --------------------------------------------------
    cursor.execute("""
    INSERT OR IGNORE INTO schemes
        (scheme_id, name, description, state, category, min_age, max_age, max_income, marital_status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("NSP_OBC", "NSP OBC Pre-Matric Scholarship",
          "Central scholarship for OBC students studying in Class 1 to 10.",
          "ALL", "Education", None, None, 44500, None))

    cursor.execute("DELETE FROM eligibility_rules WHERE scheme_id = 'NSP_OBC'")
    for field, operator, value, rule_type, reason in [
        ("annual_income", "<=", "44500", "inclusion", "Parental/guardian annual income must not exceed ₹44,500"),
    ]:
        cursor.execute("INSERT INTO eligibility_rules (scheme_id,field,operator,value,rule_type,reason) VALUES (?,?,?,?,?,?)",
                       ("NSP_OBC", field, operator, value, rule_type, reason))

    cursor.execute("DELETE FROM scheme_questions WHERE scheme_id = 'NSP_OBC'")
    for field, question, answer_type, required in [
        ("obc_category",                "Do you belong to the OBC (Other Backward Class) category?",                   "boolean", 1),
        ("current_class",               "Which class are you currently studying in? (Enter 1 to 10)",                  "number",  1),
        ("studying_govt_school",        "Are you studying in a government or government-aided school?",                 "boolean", 1),
        ("receiving_other_scholarship", "Are you receiving any other central/state government scholarship?",             "boolean", 1),
    ]:
        cursor.execute("INSERT INTO scheme_questions (scheme_id,field,question,answer_type,required) VALUES (?,?,?,?,?)",
                       ("NSP_OBC", field, question, answer_type, required))

    cursor.execute("DELETE FROM scheme_documents WHERE scheme_id = 'NSP_OBC'")
    for doc in ["OBC Caste Certificate", "Income Certificate (parent/guardian)",
                "Previous year mark sheet", "Aadhaar Card",
                "Bank passbook (student)", "School enrolment proof"]:
        cursor.execute("INSERT INTO scheme_documents (scheme_id, document_name) VALUES (?,?)", ("NSP_OBC", doc))

    print("✅ NSP OBC Pre-Matric Scholarship seeded.")


    # ==================================================
    # DONE
    # ==================================================
    connection.commit()
    connection.close()

    print()
    print("=" * 50)
    print("✅ welfare.db is ready.")
    print("   Schemes seeded:")
    print("   1. PMKISAN   — Agriculture")
    print("   2. PMUSP     — Education (CSSS)")
    print("   3. PMJAY     — Health (two-route 2026 model)")
    print("   4. PMAYG     — Housing")
    print("   5. NREGA     — Employment")
    print("   6. PMSBY     — Insurance")
    print("   7. NSP_OBC   — Education")
    print("=" * 50)
    print()
    print("Next: python -m uvicorn main:app --reload")


if __name__ == "__main__":
    setup()
