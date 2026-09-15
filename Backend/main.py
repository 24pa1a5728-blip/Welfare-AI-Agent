import sqlite3
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()


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

    institutional_landholder: bool
    constitutional_post_holder: bool
    minister_or_legislator: bool
    mayor_or_panchayat_chairperson: bool

    government_employee: bool
    government_employee_group: str

    monthly_pension: int
    income_tax_payer: bool


@app.get("/")
def home():
    return {
        "message": "Welfare AI Backend is running!"
    }


@app.post("/profile")
def create_profile(profile: UserProfile):

    return {
        "message": "Profile received",
        "profile": profile
    }


@app.get("/schemes")
def get_schemes():

    connection = sqlite3.connect(BASE_DIR / "welfare.db")
    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    cursor.execute("SELECT * FROM schemes")

    rows = cursor.fetchall()

    connection.close()

    return [dict(row) for row in rows]


@app.post("/eligibility")
def check_eligibility(profile: UserProfile):

    connection = sqlite3.connect(BASE_DIR / "welfare.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM schemes")
    schemes = cursor.fetchall()

    eligible_schemes = []
    not_eligible_schemes = []

    for scheme in schemes:

        cursor.execute("""
        SELECT * FROM eligibility_rules
        WHERE scheme_id = ?
        """, (scheme["scheme_id"],))

        rules = cursor.fetchall()

        is_eligible = True
        reason = None
        reasons = []

        if rules:

            for rule in rules:

                field = rule["field"]
                operator = rule["operator"]
                expected_value = rule["value"]
                rule_type = rule["rule_type"]

                actual_value = getattr(profile, field)

                if isinstance(actual_value, bool):
                    expected_value = expected_value.lower() == "true"

                elif isinstance(actual_value, int):
                    expected_value = int(expected_value)

                if rule_type == "inclusion":

                    if operator == "==" and actual_value != expected_value:
                        is_eligible = False
                        reason = rule["reason"]
                        break

                    else:
                        reasons.append(rule["reason"])

                elif rule_type == "exclusion":

                    if operator == "==" and actual_value == expected_value:
                        is_eligible = False
                        reason = rule["reason"]
                        break

                    elif operator == ">=" and actual_value >= expected_value:
                        is_eligible = False
                        reason = rule["reason"]
                        break

                    elif operator == "<=" and actual_value <= expected_value:
                        is_eligible = False
                        reason = rule["reason"]
                        break

                    else:
                        reasons.append(
                            "You do not fall under this exclusion: "
                            + rule["reason"]
                        )

        # -----------------------------------------
        # If potentially eligible
        # -----------------------------------------

        if is_eligible:

            cursor.execute("""
            SELECT document_name
            FROM scheme_documents
            WHERE scheme_id = ?
            """, (scheme["scheme_id"],))

            document_rows = cursor.fetchall()

            documents = [
                row["document_name"]
                for row in document_rows
            ]

            eligible_schemes.append({
                "scheme_id": scheme["scheme_id"],
                "name": scheme["name"],
                "category": scheme["category"],
                "status": "potentially_eligible",
                "reasons": reasons,
                "documents": documents
            })

        # -----------------------------------------
        # If not eligible
        # -----------------------------------------

        else:

            not_eligible_schemes.append({
                "scheme_id": scheme["scheme_id"],
                "name": scheme["name"],
                "reason": reason
            })

    connection.close()

    return {
        "eligible_schemes": eligible_schemes,
        "not_eligible_schemes": not_eligible_schemes
    }
@app.get("/schemes/{scheme_id}/documents")
def get_scheme_documents(scheme_id: str):
    connection = sqlite3.connect(BASE_DIR / "welfare.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
    SELECT document_name
    FROM scheme_documents
    WHERE scheme_id = ?
    """, (scheme_id,))

    rows = cursor.fetchall()
    connection.close()

    return {
        "scheme_id": scheme_id,
        "documents": [row["document_name"] for row in rows]
    }
