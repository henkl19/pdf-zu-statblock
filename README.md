# Atlas Monster Importer 0.2

Windows-GUI-Prototyp für den lokalen OCR-Import gescannter Monsterhandbücher.

## Für den i7-9700K mit 32 GB RAM

Voreinstellungen: 6 parallele OCR-Prozesse, 130 DPI Schnellscan und 300 DPI Detail-OCR. Die Werte lassen sich in der Oberfläche anpassen.

## Was 0.2 verbessert

- Zweistufiger Ablauf: schnelle Erkennung aller Seiten, hohe Auflösung nur für Kandidatenseiten.
- Bis zu 12 parallele Tesseract-Aufrufe (Standard: 6).
- OCR-Cache: Bereits erkannte Seiten werden beim erneuten Start nicht nochmals gescannt.
- Anhalten und Fortsetzen.
- Vollständige Quellseiten als WebP-Bildreferenz.
- Optionale CSV-Namensprüfung gegen eine SRD-Liste.
- Alle Verarbeitung erfolgt lokal; keine Cloud/KI und keine Uploads.

## Aktuelle Grenzen

Dies ist weiterhin ein OCR-Sammel- und Vorbereitungswerkzeug. Es erstellt **noch keine fertigen Atlas-VTT-Statblöcke**. Die Ausgabe enthält OCR-Entwürfe und vollständige Quellseiten; die einzelnen Monsterillustrationen werden noch nicht automatisch isoliert. Die SRD-Prüfung ist nur ein normalisierter Namensvergleich, kein inhaltlicher Regel- oder Dublettenvergleich. OCR-Ergebnisse müssen kontrolliert werden.

## Windows-EXE bauen

Voraussetzungen: Windows 10/11, Python 3.11, Tesseract-OCR mit `deu` und `eng` Sprachdaten.

1. Projekt entpacken.
2. `build_windows.bat` starten.
3. Die EXE liegt danach unter `dist\AtlasMonsterImporter.exe`.

Alternativ kann der GitHub-Workflow `.github/workflows/build-windows.yml` manuell gestartet werden. Er erstellt ein EXE-Artefakt.

## Nutzung

1. EXE starten.
2. PDF auswählen.
3. Ausgabeordner auswählen.
4. Optional eine CSV mit Monster-Namen auswählen (Name muss in der ersten Spalte stehen).
5. Import starten. Bei Unterbrechung einfach erneut starten; der Cache bleibt im Ausgabeordner erhalten.

## Datenschutz

Die PDF, OCR-Texte und Bilder werden lokal verarbeitet und gespeichert. Die Anwendung enthält keine Online-KI-Anbindung.
