from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
import psycopg2
from datetime import datetime, timedelta
import sys

#if len(sys.argv) == 4:
#    kdnr = sys.argv[1]
#    startdatum = sys.argv[2]
#    enddatum = sys.argv[3]
#else:
#    print("Fehlende Argumente: kdnr startdatum enddatum")
#    sys.exit(1)

# Verbindung zum SQL-Server
#conn = psycopg2.connect(
#    host="192.168.40.33",
#    database="kundendatenbank",
#    user="appuser",
#    password="3A5595DD43CC7FC2E414FC6AC55260DD"
#)

#cur = conn.cursor()
# SQL-Anfrage Kundendaten
#cur.execute("SELECT name, strasse, hausnummer, plz, ort FROM kunde WHERE kdnr = %s;", (kdnr,))
#kunde_row = cur.fetchone()

# SQL-Anfrage Besuchsdaten
#cur.execute("SELECT b.termin, b.anzahl_einheiten, b.bemerkung, k.preis_pro_einheit, k.einheitsdauer_min FROM besuch b JOIN kondition k ON k.kdnr = b.kdnr WHERE b.kdnr = %s AND b.termin BETWEEN %s AND %s AND k.gueltig_bis IS NULL OR b.termin <= k.gueltig_bis AND b.termin >= k.gueltig_von ORDER BY b.termin;", (kdnr, startdatum, enddatum))
#besuche_rows = cur.fetchall()

#SQL-Anfrage Fahrtkosten
#cur.execute("SELECT DISTINCT DATE(b.termin) AS besuchsdatum, k.fahrtstrecke_km, k.km_geld, k.fahrtstrecke_km * k.km_geld AS fahrtkosten FROM besuch b JOIN kondition k ON k.kdnr = b.kdnr WHERE b.kdnr = %s AND b.termin BETWEEN %s AND %s AND k.gueltig_bis IS NULL OR b.termin <= k.gueltig_bis AND b.termin >= k.gueltig_von ORDER BY besuchsdatum;", (kdnr, startdatum, enddatum))
#fahrt_rows = cur.fetchall()

#SQL-Anfrage Summe
#cur.execute("WITH einheitenkosten AS (SELECT SUM(b.anzahl_einheiten * k.preis_pro_einheit) AS summe_einheitenkosten FROM besuch b JOIN kondition k ON k.kdnr = b.kdnr WHERE b.kdnr = %s AND b.termin BETWEEN %s AND %s AND k.gueltig_bis IS NULL OR b.termin <= k.gueltig_bis AND b.termin >= k.gueltig_von), fahrtkosten AS (SELECT SUM(k.fahrtstrecke_km * k.km_geld) AS summe_fahrtkosten FROM (SELECT DISTINCT DATE(b.termin) AS besuchsdatum, k.fahrtstrecke_km, k.km_geld FROM besuch b JOIN kondition k ON k.kdnr = b.kdnr WHERE b.kdnr = %s AND b.termin BETWEEN %s AND %s AND k.gueltig_bis IS NULL OR b.termin <= k.gueltig_bis AND b.termin >= k.gueltig_von) AS k) SELECT ek.summe_einheitenkosten, fk.summe_fahrtkosten, (ek.summe_einheitenkosten + fk.summe_fahrtkosten) AS gesamt_summe FROM einheitenkosten ek, fahrtkosten fk;", (kdnr, startdatum, enddatum, kdnr, startdatum, enddatum))
#gesamtsumme = cur.fetchone()

# Datensammlung in Dictionary
#re_datum = datetime.now()
#frist = re_datum + timedelta(days=14)

#rechnung = {
#    "rechnung_nr": "2025-001",
#    "datum": re_datum.strftime("%d.%m.%Y"),
#    "frist": frist.strftime("%d.%m.%Y"),
#    "kunde": {
#        "name": kunde_row[0],
#        "strasse": kunde_row[1],
#        "hausnummer": kunde_row[2],
#        "plz": kunde_row[3],
#        "ort": kunde_row[4]
#    },
#    "besuche": [
#        {
#            "datum": row[0].strftime("%d.%m.%y"),
#            "preis_pro_einheit": row[3],
#            "einheiten": row[1],
#            "einheitsdauer": row[4],
#            "bemerkung": row[2]
#        }
#        for row in besuche_rows
#    ],
#    "fahrtkosten": [
#        {
#            "datum": row[0].strftime("%d.%m.%y"),
#            "fahrtstrecke": row[1],
#            "km_geld": row[2],
#            "kosten": row[3]
#        }
#        for row in fahrt_rows
#    ],
#    "summe": gesamtsumme[2]
#}



def generate_invoice(rechnung, output_path):
    # Template-Ordner setzen
    env = Environment(loader=FileSystemLoader("."))
    template = env.get_template("/templates/rechnung.html")

    # HTML mit Daten füllen
    html_content = template.render(rechnung=rechnung)
    HTML(string=html_content).write_pdf(
        output_path,
        stylesheets=[
            CSS(string='@page {size: A4; margin: 0mm 20mm 10mm 20mm; @bottom-right {content: "Seite " counter(page) " von " counter(pages); font-size: 10pt;} @bottom-center {content: "Dipl.-Psych. Katharina Kunisch M.A., Triodos Bank, DE67 5003 1000 1086 3140 09; BIC TRODDEF1"; font-size: 8pt; padding-top: 5px; }}')
        ]
    )
    #page_css = '''
    #@page {
    #    size: A4;
    #    margin: 0mm 20mm 10mm 20mm;
    #    
    #    @bottom-center {
    #        content: "Dipl.-Psych. Katharina Kunisch M.A., Triodos Bank, DE67 5003 1000 1086 3140 09; BIC TRODDEF1";
    #        font-size: 8pt;
    #        padding-top: 5px
    #    }
    #}  
    #'''

    # PDF erzeugen
    #pdf_file = f"Rechnung_{rechnung['rechnung_nr']}.pdf"
    #HTML(string=html_content).write_pdf(pdf_file, stylesheets=[CSS(string=page_css)])
    
    #print(f"✅ Rechnung erstellt: {pdf_file}")

if __name__ == "__main__":
    generate_invoice(rechnung)