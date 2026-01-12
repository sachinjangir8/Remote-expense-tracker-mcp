import json
import os
import aiosqlite
import time
import platform
from datetime import datetime
from typing import List, Optional
from fastmcp import FastMCP

# 1. Initialize Server (Remote/HTTP Mode)
mcp = FastMCP("Expense-Tracker-Pro")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "expenses.db")
CAT_FILE = os.path.join(BASE_DIR, "categories.json")

# 2. Async Database Setup
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                amount REAL,
                category TEXT,
                type TEXT CHECK(type IN ('expense', 'credit')),
                note TEXT
            )
        """)
        await db.commit()

# --- 3. RESOURCES (Read-Only Data) ---
@mcp.resource("config://categories")
async def get_categories() -> dict:
    """Provides the valid expense categories for the AI to reference."""
    with open(CAT_FILE, "r") as f:
        return json.load(f)

# --- 4. THE FULL TOOLSET (Read/Write) ---

@mcp.tool()
async def add_transaction(amount: float, category: str, subcategory: str, type: str = "expense", note: str = "") -> str:
    """Create: Adds a validated transaction to the database."""
    with open(CAT_FILE, "r") as f:
        data = json.load(f)["categories"]

    if category not in data or subcategory not in data[category]:
        return f"❌ Error: Invalid category/subcategory."

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO transactions (date, amount, category, type, note) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d"), amount, f"{category}:{subcategory}", type, note)
        )
        await db.commit()
    return f"✅ Recorded {type}: ${amount} under {category}."

@mcp.tool()
async def list_transactions(limit: int = 20) -> List[dict]:
    """Read: Fetches the most recent transactions."""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM transactions ORDER BY id DESC LIMIT ?", (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

@mcp.tool()
async def update_transaction(transaction_id: int, amount: Optional[float] = None, note: Optional[str] = None) -> str:
    """Update: Modifies an existing transaction's amount or note by ID."""
    async with aiosqlite.connect(DB_FILE) as db:
        if amount:
            await db.execute("UPDATE transactions SET amount = ? WHERE id = ?", (amount, transaction_id))
        if note:
            await db.execute("UPDATE transactions SET note = ? WHERE id = ?", (note, transaction_id))
        await db.commit()
    return f"✏️ Updated transaction {transaction_id}."

@mcp.tool()
async def delete_transaction(transaction_id: int) -> str:
    """Delete: Permanently removes a transaction record."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        await db.commit()
    return f"🗑️ Deleted transaction {transaction_id}."

@mcp.tool()
async def get_balance() -> str:
    """Analytics: Calculates total credits, expenses, and net balance."""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT type, SUM(amount) FROM transactions GROUP BY type") as cursor:
            results = {row[0]: row[1] for row in await cursor.fetchall()}
            
    credits = results.get('credit', 0.0)
    expenses = results.get('expense', 0.0)
    balance = credits - expenses
    return f"💰 Total Income: ${credits:.2f} | 💸 Total Spent: ${expenses:.2f} | 📈 Balance: ${balance:.2f}"

# --- SERVER METADATA RESOURCE ---
@mcp.resource("system://info")
async def get_server_info() -> dict:
    """Provides technical metadata about the Expense Tracker server status."""
    return {
        "status": "operational",
        "version": "2.1.0",
        "runtime": "Python " + platform.python_version(),
        "platform": platform.system(),
        "server_time": datetime.now().isoformat(),
        "mcp_type": "Remote (HTTP/SSE)",
        "capabilities": [
            "Async CRUD (aiosqlite)",
            "Standardized Categorization (categories.json)",
            "Financial Analytics (get_balance)"
        ],
        "database_connected": os.path.exists(DB_FILE)
    }
# --- 5. EXECUTION ---
if __name__ == "__main__":
    import asyncio
    # Initialize the database correctly in the async loop
    asyncio.run(init_db())
    
    # In 2026, we explicitly define the /mcp mount path for remote reliability
    mcp.run(
        transport="http", 
        host="0.0.0.0", 
        port=8000
    )