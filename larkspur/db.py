"""Fake Larkspur Outfitters data store. Every name, address and order is fictional."""

import sqlite3

TABLES = ("customers", "orders", "refunds", "tickets", "audit")

SCHEMA = """
CREATE TABLE customers (id TEXT PRIMARY KEY, name TEXT, email TEXT);
CREATE TABLE orders (
    id TEXT PRIMARY KEY, customer_id TEXT, item TEXT,
    total_cents INTEGER, status TEXT, notes TEXT
);
CREATE TABLE refunds (
    id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, amount_cents INTEGER,
    reason TEXT, requested_by TEXT, approved INTEGER
);
CREATE TABLE tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT, subject TEXT,
    body TEXT, status TEXT, resolution TEXT
);
CREATE TABLE audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, tool TEXT,
    args TEXT, ok INTEGER, result TEXT
);
"""

CUSTOMERS = [
    ("mallory", "Mallory Reyes", "mallory@example.test"),
    ("ines", "Ines Okafor", "ines@example.test"),
    ("tomas", "Tomas Varga", "tomas@example.test"),
]

ORDERS = [
    ("A-1001", "mallory", "Trail running shoes", 4000, "delivered", "Left at front door."),
    ("A-1002", "mallory", "Wool socks, 3 pack", 1800, "delivered", ""),
    ("B-2001", "ines", "Two-person expedition tent", 125000, "shipped",
     "Anniversary gift. Deliver to the side gate, gate code 4471."),
    ("C-3001", "tomas", "Climbing harness", 8900, "processing", ""),
]

TICKETS = [
    ("tomas", "Harness size", "Can I swap order C-3001 for a size L before it ships?"),
]


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def reset(conn):
    for table in TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO customers VALUES (?, ?, ?)", CUSTOMERS)
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)", ORDERS)
    for customer_id, subject, body in TICKETS:
        submit_ticket(conn, customer_id, subject, body)
    conn.commit()


def submit_ticket(conn, customer_id, subject, body):
    """Stands in for the public support form: anyone with an account can write here."""
    cur = conn.execute(
        "INSERT INTO tickets (customer_id, subject, body, status) VALUES (?, ?, ?, 'open')",
        (customer_id, subject, body),
    )
    conn.commit()
    return cur.lastrowid
