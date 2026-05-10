import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import inspect
import re

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout

try:
    from plyer import barcode as plyer_barcode
except Exception:  # pragma: no cover - optional runtime support
    plyer_barcode = None

KV = """
<OrbitRoot>:
    orientation: "vertical"
    padding: dp(12)
    spacing: dp(10)

    Spinner:
        id: section_spinner
        text: "Budget Tracker"
        values: ["Budget Tracker", "Barcode Registry"]
        size_hint_y: None
        height: dp(44)
        on_text: root.switch_section(args[1])

    BoxLayout:
        id: budget_section
        orientation: "vertical"
        spacing: dp(8)

        Label:
            text: "Record Income / Expense"
            size_hint_y: None
            height: dp(28)
            bold: True

        TextInput:
            id: amount_input
            hint_text: "Amount (e.g. 245.75)"
            multiline: False
            input_filter: "float"
            size_hint_y: None
            height: dp(42)

        Spinner:
            id: tx_type_spinner
            text: "Income"
            values: ["Income", "Expense"]
            size_hint_y: None
            height: dp(42)

        Spinner:
            id: category_spinner
            text: "General"
            values: ["General", "Groceries", "Transport", "Bills", "Health", "Entertainment", "Other"]
            size_hint_y: None
            height: dp(42)

        TextInput:
            id: note_input
            hint_text: "Note (e.g. salary, groceries)"
            multiline: False
            size_hint_y: None
            height: dp(42)

        Button:
            text: "Add Transaction"
            size_hint_y: None
            height: dp(42)
            on_release: root.add_transaction()

        Label:
            text: root.transaction_status
            size_hint_y: None
            height: dp(24)
            color: 0.8, 0.2, 0.2, 1

        Label:
            text: root.budget_summary
            halign: "left"
            valign: "middle"
            text_size: self.size
            size_hint_y: None
            height: dp(64)

        Label:
            text: root.monthly_analytics_title
            size_hint_y: None
            height: dp(28)
            bold: True

        ScrollView:
            size_hint_y: None
            height: dp(130)
            Label:
                text: root.monthly_analytics_text
                halign: "left"
                valign: "top"
                text_size: self.width, None
                size_hint_y: None
                height: max(self.texture_size[1], dp(120))

        Label:
            text: "Recent Transactions"
            size_hint_y: None
            height: dp(28)
            bold: True

        ScrollView:
            Label:
                id: tx_list_label
                text: root.transactions_text
                halign: "left"
                valign: "top"
                text_size: self.width, None
                size_hint_y: None
                height: max(self.texture_size[1], dp(180))

    BoxLayout:
        id: barcode_section
        orientation: "vertical"
        spacing: dp(8)
        opacity: 0
        disabled: True

        Label:
            text: "Register Product Barcode"
            size_hint_y: None
            height: dp(28)
            bold: True

        TextInput:
            id: barcode_input
            hint_text: "Barcode number"
            multiline: False
            size_hint_y: None
            height: dp(42)

        TextInput:
            id: product_name_input
            hint_text: "Product name"
            multiline: False
            size_hint_y: None
            height: dp(42)

        Button:
            text: "Scan Barcode with Camera"
            size_hint_y: None
            height: dp(42)
            on_release: root.scan_barcode()

        Button:
            text: "Register Barcode"
            size_hint_y: None
            height: dp(42)
            on_release: root.register_barcode()

        Label:
            text: root.barcode_status
            size_hint_y: None
            height: dp(28)
            color: 0.2, 0.6, 0.2, 1

        Label:
            text: "Saved Barcodes"
            size_hint_y: None
            height: dp(28)
            bold: True

        ScrollView:
            Label:
                id: barcode_list_label
                text: root.barcodes_text
                halign: "left"
                valign: "top"
                text_size: self.width, None
                size_hint_y: None
                height: max(self.texture_size[1], dp(200))
"""


class OrbitStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tx_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL DEFAULT 'General',
                    month_key TEXT NOT NULL DEFAULT '',
                    note TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS barcodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    product_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

            columns = [row[1] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()]
            if "category" not in columns:
                self._ensure_column(
                    conn, "category", "ALTER TABLE transactions ADD COLUMN category TEXT NOT NULL DEFAULT 'General'"
                )
            if "month_key" not in columns:
                self._ensure_column(
                    conn, "month_key", "ALTER TABLE transactions ADD COLUMN month_key TEXT NOT NULL DEFAULT ''"
                )

            rows = conn.execute(
                "SELECT id, created_at FROM transactions WHERE month_key = ''"
            ).fetchall()
            for row_id, created_at in rows:
                conn.execute(
                    "UPDATE transactions SET month_key = ? WHERE id = ?",
                    (self._derive_month_key(created_at), row_id),
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_transactions_month_key_type_category ON transactions(month_key, tx_type, category)"
            )

    def _ensure_column(self, conn: sqlite3.Connection, column_name: str, alter_sql: str):
        try:
            conn.execute(alter_sql)
        except sqlite3.OperationalError:
            columns = [row[1] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()]
            if column_name not in columns:
                raise

    def _derive_month_key(self, timestamp: str) -> str:
        """Best-effort month extraction expecting ISO-8601 (`YYYY-MM-...`) timestamps."""
        try:
            return datetime.fromisoformat(timestamp).strftime("%Y-%m")
        except (TypeError, ValueError):
            ts = str(timestamp or "")
            if re.match(r"^\d{4}-\d{2}", ts):
                return ts[:7]
            return datetime.now(timezone.utc).strftime("%Y-%m")

    def _get_current_timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def add_transaction(self, tx_type: str, amount: float, category: str, note: str):
        with self._connect() as conn:
            current_ts = self._get_current_timestamp()
            conn.execute(
                "INSERT INTO transactions (tx_type, amount, category, month_key, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (tx_type, amount, category, current_ts[:7], note, current_ts),
            )

    def fetch_transactions(self, limit: int = 20):
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT tx_type, amount, category, note, created_at FROM transactions ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return cursor.fetchall()

    def get_totals(self):
        with self._connect() as conn:
            income = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE tx_type = 'Income'"
            ).fetchone()[0]
            expense = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE tx_type = 'Expense'"
            ).fetchone()[0]
        return float(income), float(expense), float(income - expense)

    def get_monthly_analytics(self, month_key: str):
        with self._connect() as conn:
            income = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE tx_type = 'Income' AND month_key = ?",
                (month_key,),
            ).fetchone()[0]
            expense = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE tx_type = 'Expense' AND month_key = ?",
                (month_key,),
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT tx_type, category, COALESCE(SUM(amount), 0) AS total
                FROM transactions
                WHERE month_key = ?
                GROUP BY tx_type, category
                ORDER BY tx_type, total DESC
                """,
                (month_key,),
            ).fetchall()
        return float(income), float(expense), float(income - expense), rows

    def add_barcode(self, code: str, product_name: str) -> bool:
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO barcodes (code, product_name, created_at) VALUES (?, ?, ?)",
                    (code, product_name, self._get_current_timestamp()),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def fetch_barcodes(self, limit: int = 30):
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT code, product_name FROM barcodes ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return cursor.fetchall()


class OrbitRoot(BoxLayout):
    budget_summary = StringProperty("")
    transactions_text = StringProperty("No transactions yet.")
    monthly_analytics_title = StringProperty("Current Month Analytics")
    monthly_analytics_text = StringProperty("No transactions yet this month.")
    barcodes_text = StringProperty("No barcodes yet.")
    barcode_status = StringProperty("")
    transaction_status = StringProperty("")
    CURRENCY = "₱"

    def __init__(self, store: OrbitStore, **kwargs):
        super().__init__(**kwargs)
        self.store = store
        self.budget_summary = self._format_budget_summary(0.0, 0.0, 0.0)
        self.refresh_budget()
        self.refresh_barcodes()

    def switch_section(self, section_name: str):
        budget = self.ids.budget_section
        barcode = self.ids.barcode_section

        is_budget = section_name == "Budget Tracker"
        budget.opacity = 1 if is_budget else 0
        budget.disabled = not is_budget
        barcode.opacity = 0 if is_budget else 1
        barcode.disabled = is_budget

    def add_transaction(self):
        amount_text = self.ids.amount_input.text.strip()
        note = self.ids.note_input.text.strip()
        category = self.ids.category_spinner.text
        tx_type = self.ids.tx_type_spinner.text

        if not amount_text:
            self.transaction_status = "Please enter a valid amount (e.g., 245.75)."
            return

        try:
            amount = float(amount_text)
        except ValueError:
            self.transaction_status = "Amount must be a number."
            return

        if amount <= 0:
            self.transaction_status = "Amount must be greater than 0."
            return

        self.store.add_transaction(tx_type=tx_type, amount=amount, category=category, note=note)
        self.ids.amount_input.text = ""
        self.ids.note_input.text = ""
        self.transaction_status = "Transaction saved."
        self.refresh_budget()

    def scan_barcode(self):
        if plyer_barcode is None:
            self.barcode_status = "Camera barcode scanner unavailable. Use manual barcode input."
            return

        self.barcode_status = "Opening camera scanner..."
        try:
            scan_fn = plyer_barcode.scan
            supports_callback = False
            try:
                supports_callback = len(inspect.signature(scan_fn).parameters) >= 1
            except (TypeError, ValueError):
                supports_callback = False

            if supports_callback:
                scan_fn(self._on_barcode_scanned)
                return

            result = scan_fn()
            if not self._apply_scan_result_from_object(result):
                self.barcode_status = "No barcode detected."
        except TypeError:
            result = plyer_barcode.scan()
            if not self._apply_scan_result_from_object(result):
                self.barcode_status = "No barcode detected."
        except PermissionError:
            self.barcode_status = "Camera permission denied. Enable camera permission and retry."
        except NotImplementedError:
            self.barcode_status = "Barcode scanner is not supported on this device. Use manual barcode input."
        except Exception:
            self.barcode_status = "Scanner failed. Use manual barcode input."

    def _on_barcode_scanned(self, scanned_data):
        code = self._extract_scanned_code(scanned_data)
        if code:
            Clock.schedule_once(lambda _dt: self._apply_scan_result(code, "Scanned barcode captured."))
        else:
            Clock.schedule_once(lambda _dt: self._apply_scan_result("", "No barcode detected."))

    def _extract_scanned_code(self, scanned_data) -> str:
        if isinstance(scanned_data, str):
            return scanned_data.strip()
        if isinstance(scanned_data, dict):
            for key in ("data", "text"):
                if key in scanned_data and scanned_data[key] is not None:
                    return str(scanned_data[key]).strip()
            return ""
        if isinstance(scanned_data, (list, tuple)) and scanned_data:
            return str(scanned_data[0]).strip()
        if scanned_data is None:
            return ""
        return str(scanned_data).strip()

    def _apply_scan_result_from_object(self, scanned_data) -> bool:
        code = self._extract_scanned_code(scanned_data)
        if not code:
            return False
        self._apply_scan_result(code, "Scanned barcode captured.")
        return True

    def _apply_scan_result(self, code: str, message: str):
        if code:
            self.ids.barcode_input.text = code
        self.barcode_status = message

    def register_barcode(self):
        code = self.ids.barcode_input.text.strip()
        product_name = self.ids.product_name_input.text.strip()

        if not code or not product_name:
            self.barcode_status = "Please enter both barcode and product name."
            return

        added = self.store.add_barcode(code, product_name)
        if added:
            self.ids.barcode_input.text = ""
            self.ids.product_name_input.text = ""
            self.barcode_status = "Barcode saved."
        else:
            self.barcode_status = "Barcode already exists."
        self.refresh_barcodes()

    def refresh_budget(self):
        income, expense, balance = self.store.get_totals()
        self.budget_summary = self._format_budget_summary(income, expense, balance)

        transactions = self.store.fetch_transactions(limit=20)
        if not transactions:
            self.transactions_text = "No transactions yet."
            self.refresh_monthly_analytics()
            return

        lines = []
        for tx_type, amount, category, note, created_at in transactions:
            try:
                ts = datetime.fromisoformat(created_at).strftime("%Y-%m-%d %H:%M")
            except ValueError:
                ts = created_at
            note_part = f" - {note}" if note else ""
            lines.append(
                f"[{ts}] {tx_type} ({category}): {self.CURRENCY}{amount:,.2f}{note_part}"
            )
        self.transactions_text = "\n".join(lines)
        self.refresh_monthly_analytics()

    def refresh_monthly_analytics(self):
        month_key = datetime.now(timezone.utc).strftime("%Y-%m")
        income, expense, balance, rows = self.store.get_monthly_analytics(month_key)
        self.monthly_analytics_title = f"Current Month Analytics ({month_key})"

        if not rows:
            self.monthly_analytics_text = "No transactions yet this month."
            return

        lines = [
            f"Income: {self.CURRENCY}{income:,.2f}",
            f"Expense: {self.CURRENCY}{expense:,.2f}",
            f"Balance: {self.CURRENCY}{balance:,.2f}",
            "",
            "Breakdown by category:",
        ]
        for tx_type, category, total in rows:
            lines.append(f"- {tx_type} | {category}: {self.CURRENCY}{float(total):,.2f}")

        self.monthly_analytics_text = "\n".join(lines)

    def _format_budget_summary(self, income: float, expense: float, balance: float) -> str:
        return (
            f"Income: {self.CURRENCY}{income:,.2f} | Expense: {self.CURRENCY}{expense:,.2f} | Balance: {self.CURRENCY}{balance:,.2f}"
        )

    def refresh_barcodes(self):
        rows = self.store.fetch_barcodes(limit=30)
        if not rows:
            self.barcodes_text = "No barcodes yet."
            return

        self.barcodes_text = "\n".join([f"{code} - {name}" for code, name in rows])


class OrbitApp(App):
    title = "Orbit"

    def build(self):
        Builder.load_string(KV)
        db_path = Path(self.user_data_dir) / "orbit.db"
        store = OrbitStore(db_path=db_path)
        return OrbitRoot(store=store)


if __name__ == "__main__":
    OrbitApp().run()
