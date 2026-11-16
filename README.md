# Atlas Monster Importer 0.1

Windows-GUI zum OCR-Auslesen gescannter Monsterhandbuch-PDFs und Erstellen von Obsidian-Markdown-Entwürfen.

## Aktueller Funktionsumfang
- PDF-Seitenbereich wählbar; `Endseite = 0` verarbeitet alle Seiten.
- OCR mit Tesseract (Deutsch + Englisch voreingestellt).
- Erkennung möglicher Monster-Statblockseiten anhand von OCR-Schlüsselbegriffen.
- Pro Kandidat eine Markdown-Entwurfsnotiz, OCR-Rohtext, PDF-Seitenreferenz und ein WebP-Bild der vollständigen Seite.
- Optionaler SRD-Namensabgleich gegen eine vom Nutzer bereitgestellte CSV-Datei (Monstername in der ersten Spalte).
- CSV-Importindex und README im Ausgabeordner.

## Wichtige Einschränkungen dieser ersten Version
Dies ist bewusst ein **OCR-/Sichtungsimporter**, noch kein verlustfreier Parser fertiger Atlas-VTT-Statblöcke. Die OCR-Ausgabe muss gegen das Buch geprüft werden. Die Erkennung kann Seiten übersehen oder falsche Kandidaten finden. Die Bilddatei zeigt die ganze Seite, nicht automatisch nur die Monsterillustration. Der SRD-Abgleich ist nur ein normalisierter Namensvergleich, keine semantische Dublettenprüfung. Es werden keine `statblock: true`-Notizen ausgegeben, damit unvollständige OCR-Daten nicht versehentlich als fertige Monster in Atlas VTT erscheinen.

## EXE bauen
### Einfachster Weg: GitHub Actions
1. Diesen Projektordner in ein neues GitHub-Repository hochladen.
2. In GitHub `Actions` öffnen.
3. Workflow `Build Windows EXE` auswählen und `Run workflow` starten.
4. Nach erfolgreichem Lauf das Artefakt `AtlasMonsterImporter-Windows` herunterladen. Darin liegt `AtlasMonsterImporter.exe`.

### Lokal auf Windows
Voraussetzungen: Python 3.11 und Chocolatey. `build_windows.bat` doppelklicken. Die EXE liegt danach unter `dist\AtlasMonsterImporter.exe`.

## Bedienung
1. EXE starten.
2. Monsterhandbuch-PDF auswählen.
3. Ausgabeordner auswählen.
4. Optional SRD-CSV auswählen (Monstername in Spalte 1).
5. Seitenbereich wählen; `Endseite 0` bedeutet alle Seiten.
6. Import starten.
7. Markdown-Entwürfe im Ordner `Monster-Entwuerfe` in Obsidian prüfen.

Für das 386-seitige Scan-PDF kann die OCR je nach Rechner etliche Minuten dauern. Ein niedriger DPI-Wert ist schneller; 200 DPI ist ein Startwert.
