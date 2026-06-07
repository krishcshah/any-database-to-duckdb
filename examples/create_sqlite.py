import sqlite3
import os

def main():
    # Make sure examples dir exists
    os.makedirs("examples", exist_ok=True)
    
    db_path = "examples/sample.sqlite"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        item TEXT NOT NULL,
        amount REAL,
        status TEXT DEFAULT 'pending',
        FOREIGN KEY(customer_id) REFERENCES customers(id)
    )
    """)
    
    # Insert dummy data
    cursor.executemany("INSERT INTO customers (name, email) VALUES (?, ?)", [
        ("Alice Cooper", "alice@cooper.com"),
        ("Bob Marley", "bob@marley.com"),
        ("Charlie Chaplin", "charlie@chaplin.com")
    ])
    
    cursor.executemany("INSERT INTO orders (customer_id, item, amount, status) VALUES (?, ?, ?, ?)", [
        (1, "Wireless Mouse", 25.50, "completed"),
        (1, "Mechanical Keyboard", 120.00, "completed"),
        (2, "USB-C Hub", 45.00, "pending"),
        (3, "4K Monitor", 349.99, "completed")
    ])
    
    conn.commit()
    conn.close()
    print("Created examples/sample.sqlite successfully.")

if __name__ == "__main__":
    main()
