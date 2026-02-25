from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import Form
import os
from pydantic import BaseModel
import psycopg2
from datetime import datetime
from typing import List, Optional
import subprocess

# --- FastAPI-Setup ---
app = FastAPI()

# --- DB-Verbindung ---
def get_connection():
    return psycopg2.connect(
        host="192.168.40.33",
        database="kundendatenbank",
        user="appuser",
        password="3A5595DD43CC7FC2E414FC6AC55260DD"
    )

# --- Request-Modell ---
class Besuch(BaseModel):
    kdnr: int
    termin: datetime
    anzahl_einheiten: int
    bemerkung: str

# --- Route: Besuch speichern ---
@app.post("/besuch")
def create_besuch(besuch: Besuch):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO besuch (kdnr, termin, anzahl_einheiten, bemerkung)
        VALUES (%s, %s, %s, %s)
        """,
        (besuch.kdnr, besuch.termin, besuch.anzahl_einheiten, besuch.bemerkung)
    )

    conn.commit()
    cur.close()
    conn.close()

    return {"status": "ok", "besuch": besuch.dict()}

# Static files mounten
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/form")
def serve_form():
    return FileResponse(os.path.join("static", "form.html"))

# Kundendaten für Dropdown
@app.get("/kunden")
def get_kunden():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT kdnr, name FROM kunde ORDER BY kdnr;")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [{"kdnr": r[0], "name": r[1]} for r in rows]

# Neuen Kunden anlegen
class KundeCreate(BaseModel):
    name: str
    kuerzel: str
    ansprechpartner: Optional[str] = None
    strasse: str
    hausnummer: str
    plz: str
    ort: str

@app.post("/kunde")
def add_kunde(kunde: KundeCreate):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO kunde (name, ansprechpartner, strasse, hausnummer, plz, ort, kuerzel) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING kdnr;",
            (kunde.name, kunde.ansprechpartner, kunde.strasse, kunde.hausnummer, kunde.plz, kunde.ort, kunde.kuerzel)
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        
        return {"message": "Kunde angelegt", "kdnr": new_id}
    
    except psycopg2.Error as e:
        # Fängt spezifische Datenbank-Fehler ab
        if 'conn' in locals() and conn:
            conn.rollback() # Bricht die fehlerhafte Transaktion ab
        return {"error": "Datenbank-Fehler", "details": str(e)}
    except Exception as e:
        # Fängt sonstige Fehler ab
        return {"error": "Allgemeiner Fehler", "details": str(e)}
    finally:
        # Wird IMMER ausgeführt, um die Verbindung sauber zu schließen
        if 'cur' in locals() and cur:
            cur.close()
        if 'conn' in locals() and conn:
            conn.close()
        

# @app.get("/rechnung")
# def serve_rechnung_form():
#     return FileResponse(os.path.join("static", "rechnung.html"))

# @app.post("/rechnung")
# def create_rechnung(kdnr: int = Form(...), startdatum: str = Form(...), enddatum: str = Form(...)):
    # Rufe dein bestehendes Python-Skript auf (z. B. generate_invoice.py)
    # oder eine Funktion aus dieser Datei, wenn du sie hier importierst.
#     try:
#         subprocess.run(
#             ["python3", "generate_invoice.py", str(kdnr), startdatum, enddatum],
#             check=True
#         )
#         return {"message": "✅ Rechnung erfolgreich erstellt"}
#     except subprocess.CalledProcessError as e:
#         return {"error": f"Fehler bei der Rechnungserstellung: {e}"}
