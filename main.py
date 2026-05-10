import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from kivy.app import App
from kivy.lang import Builder
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout

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
            text: root.budget_summary
            halign: "left"
            valign: "middle"
            text_size: self.size
            size_hint_y: None
            height: dp(64)

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
                height: max(self.texture_size[1], dp(200))

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
            input_filter: "int"
            size_hint_y: None
            height: dp(42)

        TextInput:
            id: product_name_input
            hint_text: "Product name"
            multiline: False
            size_hint_y: None
            height: dp(42)

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

    def add_transaction(self, tx_type: str, amount: float, note: str):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO transactions (tx_type, amount, note, created_at) VALUES (?, ?, ?, ?)",
                (tx_type, amount, note.strip(), datetime.now(timezone.utc).isoformat()),
            )

    def fetch_transactions(self, limit: int = 20):
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT tx_type, amount, note, created_at FROM transactions ORDER BY id DESC LIMIT ?",
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

    def add_barcode(self, code: str, product_name: str) -> bool:
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO barcodes (code, product_name, created_at) VALUES (?, ?, ?)",
                    (code.strip(), product_name.strip(), datetime.now(timezone.utc).isoformat()),
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
    budget_summary = StringProperty("Income: ₱0.00 | Expense: ₱0.00 | Balance: ₱0.00")
    transactions_text = StringProperty("No transactions yet.")
    barcodes_text = StringProperty("No barcodes yet.")
    barcode_status = StringProperty("")

    def __init__(self, store: OrbitStore, **kwargs):
        super().__init__(**kwargs)
        self.store = store
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
        tx_type = self.ids.tx_type_spinner.text

        if not amount_text:
            return

        try:
            amount = float(amount_text)
        except ValueError:
            return

        if amount <= 0:
            return

        self.store.add_transaction(tx_type=tx_type, amount=amount, note=note)
        self.ids.amount_input.text = ""
        self.ids.note_input.text = ""
        self.refresh_budget()

    def register_barcode(self):
        code = self.ids.barcode_input.text.strip()
        product_name = self.ids.product_name_input.text.strip()

        if not code or not product_name:
            self.barcode_status = "Please fill barcode and product."
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
        self.budget_summary = (
            f"Income: ₱{income:,.2f} | Expense: ₱{expense:,.2f} | Balance: ₱{balance:,.2f}"
        )

        transactions = self.store.fetch_transactions(limit=20)
        if not transactions:
            self.transactions_text = "No transactions yet."
            return

        lines = []
        for tx_type, amount, note, created_at in transactions:
            ts = created_at.replace("T", " ")[:16]
            note_part = f" - {note}" if note else ""
            lines.append(f"[{ts}] {tx_type}: ₱{amount:,.2f}{note_part}")
        self.transactions_text = "\n".join(lines)

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
        db_path = Path(App.get_running_app().user_data_dir) / "orbit.db"
        store = OrbitStore(db_path=db_path)
        return OrbitRoot(store=store)


if __name__ == "__main__":
    OrbitApp().run()
