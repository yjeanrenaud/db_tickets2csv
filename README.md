# db_tickets2csv
extract data from PDF tickets from Deutsche Bahn anf save them to a table
it's a small python script to extract data from PDF files provided by Deutsche Bahn and get the most important data (for me) out of them in a neat little csv file that spreadsheet apps can read.
## requirements
- python3
- pdfplumber
- pandas
- real PDF files, no photos or scans
## usage: 
```db_tickets_to_csv.py [-h] [-o OUT] [--sep SEP] [--recursive]
                            [--encoding ENCODING]
                            folder

DB Ticket PDFs -> CSV (Datum/Preis/Start/Ziel)

positional arguments:
  folder               folder containing PDF-Tickets

options:
  -h, --help           show this help message and exit
  -o OUT, --out OUT    output file CSV (Default: tickets.csv)
  --sep SEP            CSV-Trennzeichen (z.B. ';' ',' '\t' '|'). Default: ';'
  --recursive          search sufolders recursively
  --encoding ENCODING  Encoding (Default: utf-8-sig for MS Excel)
```
