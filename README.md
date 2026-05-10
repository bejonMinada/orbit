# Orbit

Orbit is a Python-based Android-ready app built with **Kivy**.

## MVP+ features
- Budget tracking (income and expense entries)
- Running totals (income, expense, balance)
- Budget category tagging per transaction
- Current-month analytics with category breakdown
- Product barcode registry in a separate dropdown section
- Camera barcode scanning support (device/OS dependent, with manual fallback)
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

## Notes
- Marketplace price comparison (Shopee/Lazada/etc.) is not included yet because a reliable forever-free integration cannot be guaranteed for production usage.
