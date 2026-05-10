# Orbit

Orbit is a Python-based Android-ready MVP app built with **Kivy**.

## MVP features
- Budget tracking (income and expense entries)
- Running totals (income, expense, balance)
- Product barcode registry in a separate dropdown section
- Local persistence using SQLite

## Run locally
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the app:
   ```bash
   python main.py
   ```

## Build APK (Android)
Use Buildozer on Linux:

1. Install Buildozer and Android prerequisites.
2. In the project root, run:
   ```bash
   buildozer android debug
   ```
3. The generated `.apk` is created in the `bin/` directory.

## Notes for next phase
Potential next features after MVP:
- Barcode scanning through camera integration (instead of manual barcode entry)
- Price comparison from marketplaces (Shopee, Lazada, etc.)
- Budget categories and monthly insights
- Cloud sync and backup
