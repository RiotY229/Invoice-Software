import psycopg2
import configparser
from datetime import datetime, timedelta
from pprint import pprint

# --- Konfiguration einlesen ---
config = configparser.ConfigParser()
config.read("config.ini")

db_cfg = config["database"]

# --- Verbindungsfunktion ---
def get_connection():
    conn = psycopg2.connect(
        host=db_cfg["host"],
        port=db_cfg.get("port", 5432),
        database=db_cfg["database"],
        user=db_cfg["user"],
        password=db_cfg["password"]
    )
    return conn

def fetch_kunden():
    """
    Holt alle Kunden aus der Datenbank und gibt eine Liste von Dictionaries zurück.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()  # Cursor = "Steuerungselement" für SQL-Abfragen

        cur.execute("SELECT kdnr, name FROM kunde ORDER BY kdnr;")
        rows = cur.fetchall()  # Holt alle Zeilen der Ergebnistabelle

        kunden = [{"kdnr": row[0], "name": row[1]} for row in rows]

        cur.close()
        conn.close()

        return kunden
    except Exception as e:
        print("❌ Fehler beim Abrufen der Kunden:", e)
        return []

def fetch_rechnungsdaten(kdnr: int, startdatum: str, enddatum: str):
    """
    Holt alle Daten, die für die Rechnung eines Kunden im angegebenen Zeitraum benötigt werden.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Kundendaten
    cur.execute("SELECT name, strasse, hausnummer, plz, ort, ansprechpartner, kuerzel FROM kunde WHERE kdnr = %s;", (kdnr,))
    kunde_row = cur.fetchone()
    
    # Besuchsdaten
    cur.execute("SELECT b.termin, b.anzahl_einheiten, b.bemerkung, k.preis_pro_einheit, k.einheitsdauer_min FROM besuch b JOIN kondition k ON k.kdnr = b.kdnr WHERE b.kdnr = %s AND b.termin BETWEEN %s AND %s AND k.gueltig_bis IS NULL OR b.termin <= k.gueltig_bis AND b.termin >= k.gueltig_von ORDER BY b.termin;", (kdnr, startdatum, enddatum))
    besuche_rows = cur.fetchall()
    
    # Fahrtkosten (ein Eintrag pro Besuchstag)
    cur.execute("SELECT DISTINCT DATE(b.termin) AS besuchsdatum, k.fahrtstrecke_km, k.km_geld, k.fahrtstrecke_km * k.km_geld AS fahrtkosten FROM besuch b JOIN kondition k ON k.kdnr = b.kdnr WHERE b.kdnr = %s AND b.termin BETWEEN %s AND %s AND k.gueltig_bis IS NULL OR b.termin <= k.gueltig_bis AND b.termin >= k.gueltig_von ORDER BY besuchsdatum;", (kdnr, startdatum, enddatum))
    fahrt_rows = cur.fetchall()

    
    # Gesamtkosten
    cur.execute("WITH einheitenkosten AS (SELECT SUM(b.anzahl_einheiten * k.preis_pro_einheit) AS summe_einheitenkosten FROM besuch b JOIN kondition k ON k.kdnr = b.kdnr WHERE b.kdnr = %s AND b.termin BETWEEN %s AND %s AND k.gueltig_bis IS NULL OR b.termin <= k.gueltig_bis AND b.termin >= k.gueltig_von), fahrtkosten AS (SELECT SUM(k.fahrtstrecke_km * k.km_geld) AS summe_fahrtkosten FROM (SELECT DISTINCT DATE(b.termin) AS besuchsdatum, k.fahrtstrecke_km, k.km_geld FROM besuch b JOIN kondition k ON k.kdnr = b.kdnr WHERE b.kdnr = %s AND b.termin BETWEEN %s AND %s AND k.gueltig_bis IS NULL OR b.termin <= k.gueltig_bis AND b.termin >= k.gueltig_von) AS k) SELECT ek.summe_einheitenkosten, fk.summe_fahrtkosten, (ek.summe_einheitenkosten + fk.summe_fahrtkosten) AS gesamt_summe FROM einheitenkosten ek, fahrtkosten fk;", (kdnr, startdatum, enddatum, kdnr, startdatum, enddatum))
    gesamtsumme = cur.fetchone()
    
    cur.close()
    conn.close()
    
    # Datenstruktur für Template
    re_datum = datetime.now()
    frist = re_datum + timedelta(days=14)
    
    rechnung = {
        "rechnung_nr": f"{kunde_row[6]}{datetime.now().strftime("%y-%m")}",
        "datum": re_datum.strftime("%d.%m.%Y"),
        "frist": frist.strftime("%d.%m.%Y"),
        "kunde": {
            "name": kunde_row[0],
            "ansprechpartner": kunde_row[5],
            "strasse": kunde_row[1],
            "hausnummer": kunde_row[2],
            "plz": kunde_row[3],
            "ort": kunde_row[4]
        },
        "besuche": [
            {
                "datum": row[0].strftime("%d.%m.%y"),
                "preis_pro_einheit": row[3],
                "einheiten": row[1],
                "einheitsdauer": row[4],
                "bemerkung": row[2]
            }
            for row in besuche_rows
        ],
        "fahrtkosten": [
            {
                "datum": row[0].strftime("%d.%m.%y"),
                "fahrtstrecke": row[1],
                "km_geld": row[2],
                "kosten": row[3]
            }
            for row in fahrt_rows
#            if all(x is not None for x in row[1:4]) and row[3] > 0
        ],
        "summe": gesamtsumme[2]
    }
    
    return rechnung
    
# --- Test ---
if __name__ == "__main__":
    try:
        conn = get_connection()
        print("✅ Verbindung erfolgreich!")
        conn.close()
    except Exception as e:
        print("❌ Verbindung fehlgeschlagen:", e)
        
    try:
        kunden = fetch_kunden()
        for k in kunden:
            print(f"{k['kdnr']}: {k['name']}")
    except Exception as e:
        print("❌ Fehler beim Abrufen:", e)
    
    r = fetch_rechnungsdaten(10001, "2025-01-01", "2025-10-08")
    pprint(r)