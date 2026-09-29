from fastapi import FastAPI, Query
import duckdb
import re
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()
con = None
executor = ThreadPoolExecutor(max_workers=4)

SEARCH_COLUMNS = {
    "mobile": "mobile",
    "alt": "alt",
    "id": "id",
    "email": "email",
}
VALID_TYPES = list(SEARCH_COLUMNS.keys())

PARQUET_URL = "https://huggingface.co/datasets/tfqdeadlo/Inddatainonefile/resolve/main/users_data.parquet"


def init_db():
    global con
    if con is None:
        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs;")
        con.execute(
            f"CREATE OR REPLACE VIEW users AS SELECT * FROM read_parquet('{PARQUET_URL}')"
        )
    return con


@app.get("/")
def home():
    return {
        "status": "online",
        "message": "User Search API",
        "endpoints": {
            "search": "/search?type=mobile&q=9876543210&limit=100",
            "types": VALID_TYPES,
        },
    }


@app.get("/search")
def search(
    q: str = Query(..., description="Search value"),
    type: str = Query("mobile", description=f"Search type: {VALID_TYPES}"),
    limit: int = Query(100, description="Max results"),
):
    q_clean = str(q).strip()
    type_clean = str(type).strip().lower()
    limit_clean = min(max(limit, 1), 500)

    if type_clean not in VALID_TYPES:
        return {"success": False, "message": f"Invalid type. Valid: {VALID_TYPES}"}

    if type_clean in ("mobile", "alt") and not re.match(r"^\d{10}$", q_clean):
        return {"success": False, "message": "Number must be 10 digits"}

    if type_clean == "id" and not re.match(r"^\d{12}$", q_clean):
        return {"success": False, "message": "Aadhar ID must be 12 digits"}

    if type_clean == "email" and not re.match(r"^[^@]+@[^@]+\.[^@]+$", q_clean):
        return {"success": False, "message": "Invalid email format"}

    init_db()
    future = executor.submit(_search_db, q_clean, type_clean, limit_clean)
    return future.result()


def _search_db(q: str, type: str, limit: int = 100):
    try:
        col = SEARCH_COLUMNS[type]
        query = f"""
            SELECT mobile, name, fname AS father_name, address, circle,
                   alt AS alternate, id AS aadhar, email
            FROM users WHERE {col} = ? LIMIT ?
        """
        results = con.execute(query, [q, limit]).fetchall()

        if not results:
            return {"success": False, "message": f"{type} '{q}' not found"}

        columns = ["mobile", "name", "father_name", "address",
                   "circle", "alternate", "aadhar", "email"]
        rows = [dict(zip(columns, row)) for row in results]

        return {"success": True, "number": q, "total": len(rows), "results": rows}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/stats")
def stats():
    try:
        init_db()
        count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        return {"status": "success", "total_records": count}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/health")
def health():
    try:
        init_db()
        con.execute("SELECT 1").fetchone()
        return {"status": "healthy", "database": "connected"}
    except:
        return {"status": "unhealthy"}
