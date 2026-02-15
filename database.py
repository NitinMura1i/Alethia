import sqlite3
import json
from datetime import datetime

DB_PATH = "pinnacle.db"


def get_connection():
    """Get a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the database tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT UNIQUE,
            address TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_phone TEXT,
            role TEXT,
            content TEXT,
            tool_calls TEXT,
            tool_call_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            confirmation_number TEXT UNIQUE,
            customer_name TEXT,
            customer_phone TEXT,
            address TEXT,
            service_category TEXT,
            issue_description TEXT,
            preferred_date TEXT,
            preferred_time TEXT,
            urgency TEXT,
            status TEXT DEFAULT 'confirmed',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# --- Customer Functions ---

def get_customer(phone):
    """Look up a customer by phone number."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM customers WHERE phone = ?", (phone,))
    customer = cursor.fetchone()
    conn.close()
    return dict(customer) if customer else None


def save_customer(name, phone, address=None):
    """Save or update a customer record."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO customers (name, phone, address)
        VALUES (?, ?, ?)
        ON CONFLICT(phone) DO UPDATE SET
            name = excluded.name,
            address = COALESCE(excluded.address, customers.address)
    """, (name, phone, address))
    conn.commit()
    conn.close()


# --- Conversation Functions ---

def save_message(customer_phone, message):
    """Save a single message to the conversation history."""
    conn = get_connection()
    cursor = conn.cursor()

    tool_calls = None
    if message.get("tool_calls"):
        tool_calls = json.dumps(message["tool_calls"])

    cursor.execute("""
        INSERT INTO conversations (customer_phone, role, content, tool_calls, tool_call_id)
        VALUES (?, ?, ?, ?, ?)
    """, (
        customer_phone,
        message["role"],
        message.get("content"),
        tool_calls,
        message.get("tool_call_id")
    ))
    conn.commit()
    conn.close()


def get_conversation_history(customer_phone, limit=20):
    """Load recent conversation history for a customer.

    Returns the last `limit` messages to keep context manageable.
    In production, you'd use summarization for older messages.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT role, content, tool_calls, tool_call_id
        FROM conversations
        WHERE customer_phone = ?
        ORDER BY id DESC
        LIMIT ?
    """, (customer_phone, limit))
    rows = cursor.fetchall()
    conn.close()

    # Reverse so they're in chronological order
    messages = []
    for row in reversed(rows):
        msg = {"role": row["role"], "content": row["content"]}
        if row["tool_calls"]:
            msg["tool_calls"] = json.loads(row["tool_calls"])
        if row["tool_call_id"]:
            msg["tool_call_id"] = row["tool_call_id"]
        messages.append(msg)

    return messages


# --- Booking Functions ---

def save_booking(booking_data):
    """Save a booking to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO bookings (
            confirmation_number, customer_name, customer_phone, address,
            service_category, issue_description, preferred_date,
            preferred_time, urgency, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        booking_data["confirmation_number"],
        booking_data["customer_name"],
        booking_data.get("phone", ""),
        booking_data["address"],
        booking_data["service_category"],
        booking_data["issue_description"],
        booking_data["preferred_date"],
        booking_data["preferred_time"],
        booking_data["urgency"],
        booking_data["status"]
    ))
    conn.commit()
    conn.close()


def get_customer_bookings(phone):
    """Get all bookings for a customer."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM bookings
        WHERE customer_phone = ?
        ORDER BY created_at DESC
    """, (phone,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
