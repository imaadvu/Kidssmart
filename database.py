import sqlite3

DB = "search_results.db"

def create_database():
    with sqlite3.connect(DB) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS results(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT,
                title TEXT,
                link TEXT,
                content TEXT
            )
        """)

def save_result(query, title, link, content):
    with sqlite3.connect(DB) as con:
        con.execute(
            "INSERT INTO results(query,title,link,content) VALUES (?,?,?,?)",
            (query, title, link, content or "")
        )

def get_results():
    with sqlite3.connect(DB) as con:
        return con.execute(
            "SELECT id, query, title, link, content FROM results ORDER BY id DESC"
        ).fetchall()

if __name__ == "__main__":
    create_database()
    print("Database setup completed.")
