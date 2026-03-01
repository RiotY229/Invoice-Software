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
    cur.execute("""
        SELECT b.termin, b.anzahl_einheiten, b.bemerkung, k.preis_pro_einheit, k.einheitsdauer_min, k.kondition_id
        FROM besuch b 
        JOIN kondition k ON k.kdnr = b.kdnr 
        WHERE b.kdnr = %s 
            AND b.termin BETWEEN %s AND %s 
            AND b.termin >= k.gueltig_von 
            AND (k.gueltig_bis IS NULL OR b.termin <= k.gueltig_bis) 
        ORDER BY b.termin;
    """, (kdnr, startdatum, enddatum))
    besuche_rows = cur.fetchall()
    
    # Fahrtkosten (ein Eintrag pro Besuchstag)
    cur.execute("""
        SELECT DISTINCT DATE(b.termin) AS besuchsdatum, k.fahrtstrecke_km, k.km_geld, k.fahrtstrecke_km * k.km_geld AS fahrtkosten
        FROM besuch b
        JOIN kondition k ON k.kdnr = b.kdnr
        WHERE b.kdnr = %s
            AND b.termin BETWEEN %s AND %s 
            AND b.termin >= k.gueltig_von 
            AND (k.gueltig_bis IS NULL OR b.termin <= k.gueltig_bis) 
        ORDER BY besuchsdatum;
    """, (kdnr, startdatum, enddatum))
    fahrt_rows = cur.fetchall()

    # Gesamtkosten
    cur.execute("""
        WITH einheitenkosten AS (
            SELECT SUM(b.anzahl_einheiten * k.preis_pro_einheit) AS summe_einheitenkosten
            FROM besuch b
            JOIN kondition k ON k.kdnr = b.kdnr
            WHERE b.kdnr = %s
                AND b.termin BETWEEN %s AND %s
                AND b.termin >= k.gueltig_von
                AND (k.gueltig_bis IS NULL OR b.termin <= k.gueltig_bis)
            ),
            fahrtkosten AS (
                SELECT SUM(k.fahrtstrecke_km * k.km_geld) AS summe_fahrtkosten
                FROM (
                    SELECT DISTINCT DATE(b.termin) AS besuchsdatum, k.fahrtstrecke_km, k.km_geld
                    FROM besuch b
                    JOIN kondition k ON k.kdnr = b.kdnr
                    WHERE b.kdnr = %s
                        AND b.termin BETWEEN %s AND %s
                        AND b.termin >= k.gueltig_von
                        AND (k.gueltig_bis IS NULL OR b.termin <= k.gueltig_bis)
                    ) AS k
                )
            SELECT ek.summe_einheitenkosten, fk.summe_fahrtkosten, (ek.summe_einheitenkosten + fk.summe_fahrtkosten) AS gesamt_summe
            FROM einheitenkosten ek, fahrtkosten fk;
        """, (kdnr, startdatum, enddatum, kdnr, startdatum, enddatum))
    gesamtsumme = cur.fetchone()
    
    cur.close()
    conn.close()
    
    # Datenstruktur für Template
    re_datum = datetime.now()
    frist = re_datum + timedelta(days=14)
    
    rechnung = {
        "rechnung_nr": f"{kunde_row[6]}{datetime.now().strftime('%y-%m')}",
        "datum": re_datum.strftime("%d.%m.%Y"),
        "frist": frist.strftime("%d.%m.%Y"),
        "kondition_id": besuche_rows[0][5] if len(besuche_rows) > 0 else None,
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

# Funktionen für Rechnungs-Tracking
def check_invoice_paid(rechnung_nr: str) -> bool:
    """Prüft, ob eine Rechnung bereits als bezahlt markiert wurde."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT bezahlt FROM rechnung WHERE rechnung_nr = %s;", (rechnung_nr,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else False

def upsert_rechnung(rechnung: dict, kdnr: int):
    """Speichert eine neue Rechnung oder überschreibt eine unbezahlte (Upsert)."""
    conn = get_connection()
    cur = conn.cursor()

    # Snapshot-Daten sicher extrahieren (falls mal keine Besuche, aber Fahrtkosten da sind)
    preis = rechnung['besuche'][0]['preis_pro_einheit'] if rechnung['besuche'] else 0.0
    dauer = rechnung['besuche'][0]['einheitsdauer'] if rechnung['besuche'] else 0
    km = rechnung['fahrtkosten'][0]['fahrtstrecke'] if rechnung['fahrtkosten'] else 0.0
    geld = rechnung['fahrtkosten'][0]['km_geld'] if rechnung['fahrtkosten'] else 0.0
    kondition_id = rechnung.get('kondition_id')

    # ON CONFLICT nutzt deinen 'uk_rechnung_nr' Constraint!
    cur.execute("""
        INSERT INTO rechnung 
        (rechnung_nr, kdnr, kondition_id, summe, preis_pro_einheit_snapshot, einheitsdauer_min_snapshot, fahrtstrecke_km_snapshot, km_geld_snapshot, bezahlt)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false)
        ON CONFLICT (rechnung_nr) DO UPDATE SET
            summe = EXCLUDED.summe,
            kondition_id = EXCLUDED.kondition_id,
            preis_pro_einheit_snapshot = EXCLUDED.preis_pro_einheit_snapshot,
            einheitsdauer_min_snapshot = EXCLUDED.einheitsdauer_min_snapshot,
            fahrtstrecke_km_snapshot = EXCLUDED.fahrtstrecke_km_snapshot,
            km_geld_snapshot = EXCLUDED.km_geld_snapshot;
    """, (
        rechnung['rechnung_nr'], kdnr, kondition_id, rechnung['summe'], preis, dauer, km, geld
    ))
    
    conn.commit()
    cur.close()
    conn.close()

def fetch_offene_rechnungen():
    """Holt alle Rechnungen, die noch nicht bezahlt wurden."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT r.rechnung_nr, r.rechnungsdatum, k.name, r.summe 
        FROM rechnung r
        JOIN kunde k ON r.kdnr = k.kdnr
        WHERE r.bezahlt = false
        ORDER BY r.rechnungsdatum DESC;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"rechnung_nr": r[0], "datum": r[1].strftime("%d.%m.%Y"), "kunde": r[2], "summe": r[3]} for r in rows]

def mark_rechnung_bezahlt(rechnung_nr: str):
    """Markiert eine Rechnung in der Datenbank als bezahlt."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE rechnung SET bezahlt = true WHERE rechnung_nr = %s;", (rechnung_nr,))
    conn.commit()
    cur.close()
    conn.close()

# Kunden- und Konditionsverwaltung

def fetch_kunde_details(kdnr: int):
    """Holt Stammdaten und die aktuell gültigen Konditionen eines Kunden."""
    conn = get_connection()
    cur = conn.cursor()
    
    # JOIN mit kondition, aber NUR die aktuell gültige (gueltig_bis IS NULL)
    cur.execute("""
        SELECT k.name, k.kuerzel, k.ansprechpartner, k.strasse, k.hausnummer, k.plz, k.ort,
               c.preis_pro_einheit, c.einheitsdauer_min, c.fahrtstrecke_km, c.km_geld, c.gueltig_von
        FROM kunde k
        LEFT JOIN kondition c ON k.kdnr = c.kdnr AND c.gueltig_bis IS NULL
        WHERE k.kdnr = %s;
    """, (kdnr,))
    
    row = cur.fetchone()
    cur.close()
    conn.close()
    
    if not row:
        return None
        
    return {
        "name": row[0] or "", "kuerzel": row[1] or "", "ansprechpartner": row[2] or "", 
        "strasse": row[3] or "", "hausnummer": row[4] or "", "plz": row[5] or "", "ort": row[6] or "",
        "preis": row[7] if row[7] is not None else 0.0,
        "dauer": row[8] if row[8] is not None else 0,
        "strecke": row[9] if row[9] is not None else 0.0,
        "km_geld": row[10] if row[10] is not None else 0.0,
        "gueltig_von": row[11].strftime("%d.%m.%Y") if len(row) > 11 and row[11] is not None else "Unbekannt"
    }

def update_kunde_stammdaten(kdnr: int, daten: dict):
    """Aktualisiert die reinen Stammdaten eines Kunden."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE kunde 
        SET name = %s, kuerzel = %s, ansprechpartner = %s, strasse = %s, hausnummer = %s, plz = %s, ort = %s
        WHERE kdnr = %s;
    """, (
        daten['name'], daten['kuerzel'], daten['ansprechpartner'] or None, 
        daten['strasse'], daten['hausnummer'], daten['plz'], daten['ort'], kdnr
    ))
    conn.commit()
    cur.close()
    conn.close()

def update_kunde_konditionen(kdnr: int, preis: float, dauer: int, strecke: float, km_geld: float, gueltig_ab_str: str):
    """Versioniert die Konditionen: Beendet alte Kondition und legt neue an."""
    conn = get_connection()
    cur = conn.cursor()
    
    gueltig_ab = datetime.strptime(gueltig_ab_str, "%Y-%m-%d").date()
    gueltig_bis_alt = gueltig_ab - timedelta(days=1)
    
    # 1. Prüfen, ob es eine aktive Kondition gibt
    cur.execute("SELECT kondition_id FROM kondition WHERE kdnr = %s AND gueltig_bis IS NULL;", (kdnr,))
    aktive_kondition = cur.fetchone()
    
    # 2. Falls ja, beenden wir sie am Tag VOR dem neuen Startdatum
    if aktive_kondition:
        cur.execute("UPDATE kondition SET gueltig_bis = %s WHERE kondition_id = %s;", (gueltig_bis_alt, aktive_kondition[0]))
        
    # 3. Neue Kondition anlegen
    cur.execute("""
        INSERT INTO kondition (kdnr, gueltig_von, preis_pro_einheit, einheitsdauer_min, fahrtstrecke_km, km_geld)
        VALUES (%s, %s, %s, %s, %s, %s);
    """, (kdnr, gueltig_ab, preis, dauer, strecke, km_geld))
    
    conn.commit()
    cur.close()
    conn.close()

def correct_kunde_konditionen(kdnr: int, preis: float, dauer: int, strecke: float, km_geld: float):
    """Überschreibt die aktuell gültige Kondition (nur für Tippfehler, keine Historisierung)."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        UPDATE kondition 
        SET preis_pro_einheit = %s, einheitsdauer_min = %s, fahrtstrecke_km = %s, km_geld = %s
        WHERE kdnr = %s AND gueltig_bis IS NULL;
    """, (preis, dauer, strecke, km_geld, kdnr))
    
    conn.commit()
    cur.close()
    conn.close()


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