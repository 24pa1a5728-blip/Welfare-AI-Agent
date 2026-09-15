import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

connection = sqlite3.connect(BASE_DIR / "welfare.db")

connection.execute("PRAGMA foreign_keys = ON")

cursor = connection.cursor()


# --------------------------------------------------
# 1. Schemes table
# --------------------------------------------------

cursor.execute("""
CREATE TABLE IF NOT EXISTS schemes (
    scheme_id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    state TEXT,
    category TEXT,
    min_age INTEGER,
    max_age INTEGER,
    max_income INTEGER,
    marital_status TEXT
)
""")


# --------------------------------------------------
# 2. Eligibility rules table
# --------------------------------------------------

cursor.execute("""
CREATE TABLE IF NOT EXISTS eligibility_rules (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scheme_id TEXT,
    field TEXT,
    operator TEXT,
    value TEXT,
    rule_type TEXT,
    reason TEXT,
    FOREIGN KEY (scheme_id) REFERENCES schemes(scheme_id)
)
""")


# --------------------------------------------------
# 3. Scheme documents table
# --------------------------------------------------

cursor.execute("""
CREATE TABLE IF NOT EXISTS scheme_documents (
    document_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scheme_id TEXT,
    document_name TEXT,
    FOREIGN KEY (scheme_id) REFERENCES schemes(scheme_id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS applications (
    application_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scheme_id TEXT,
    applicant_name TEXT,
    age INTEGER,
    gender TEXT,
    state TEXT,
    district TEXT,
    annual_income INTEGER,
    marital_status TEXT,
    occupation TEXT,
    status TEXT,
    FOREIGN KEY (scheme_id) REFERENCES schemes(scheme_id)
)
""")


# --------------------------------------------------
# 4. Insert PM-KISAN scheme
# --------------------------------------------------

cursor.execute("""
INSERT OR IGNORE INTO schemes
(
    scheme_id,
    name,
    description,
    state,
    category,
    min_age,
    max_age,
    max_income,
    marital_status
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    "PMKISAN",
    "PM-KISAN Samman Nidhi",
    "Income support scheme for eligible landholding farmer families.",
    "ALL",
    "Agriculture",
    None,
    None,
    None,
    None
))


# --------------------------------------------------
# 5. PM-KISAN eligibility rules
# --------------------------------------------------

cursor.execute("""
DELETE FROM eligibility_rules
WHERE scheme_id = ?
""", ("PMKISAN",))


pm_kisan_rules = [

    (
        "farmer",
        "==",
        "true",
        "inclusion",
        "Applicant must be a farmer"
    ),

    (
        "institutional_landholder",
        "==",
        "true",
        "exclusion",
        "Institutional landholders are excluded"
    ),

    (
        "constitutional_post_holder",
        "==",
        "true",
        "exclusion",
        "Former or present constitutional post holders are excluded"
    ),

    (
        "minister_or_legislator",
        "==",
        "true",
        "exclusion",
        "Former or present ministers and legislators are excluded"
    ),

    (
        "mayor_or_panchayat_chairperson",
        "==",
        "true",
        "exclusion",
        "Former or present mayors and district panchayat chairpersons are excluded"
    ),

    (
        "government_employee_group",
        "==",
        "regular",
        "exclusion",
        "Regular government employees in the specified categories are excluded"
    ),

    (
        "monthly_pension",
        ">=",
        "10000",
        "exclusion",
        "Pensioners receiving a monthly pension of ₹10,000 or more are excluded"
    ),

    (
        "income_tax_payer",
        "==",
        "true",
        "exclusion",
        "Income-tax payers are excluded"
    )
]


for field, operator, value, rule_type, reason in pm_kisan_rules:

    cursor.execute("""
    INSERT INTO eligibility_rules
    (
        scheme_id,
        field,
        operator,
        value,
        rule_type,
        reason
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        "PMKISAN",
        field,
        operator,
        value,
        rule_type,
        reason
    ))


# --------------------------------------------------
# 6. PM-KISAN document / information checklist
# --------------------------------------------------

cursor.execute("""
DELETE FROM scheme_documents
WHERE scheme_id = ?
""", ("PMKISAN",))


pm_kisan_documents = [
    "Land ownership / cultivable land proof",
    "Aadhaar",
    "Bank account details",
    "Mobile number",
    "Self-declaration"
]


for document in pm_kisan_documents:

    cursor.execute("""
    INSERT INTO scheme_documents
    (
        scheme_id,
        document_name
    )
    VALUES (?, ?)
    """, (
        "PMKISAN",
        document
    ))


# --------------------------------------------------
# 7. Save changes
# --------------------------------------------------

connection.commit()

connection.close()


print("Database and schemes created successfully!")
