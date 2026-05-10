from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional
import jwt
import json
import os
import re
import httpx
from datetime import datetime, timedelta
from items import HardwareManager
from users import UserManager

# ─── Absolute DB path ────────────────────────────────────────
# Always resolves to backend/hardware.db regardless of where
# uvicorn is launched from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "hardware.db")

def get_hm(): return HardwareManager(DB_PATH)
def get_um(): return UserManager(DB_PATH)

# ─── Default admin credentials ──────────────────────────────
# Change these before deploying to production!
DEFAULT_ADMIN_USERNAME = "admin@local.com"
DEFAULT_ADMIN_PASSWORD = "admin123"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "") 

# ─── Startup: ensure admin exists ───────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on server startup (before first request).
    Creates the default admin if no admin account exists yet.
    Safe to call on every restart — it is idempotent.
    """
    um = get_um()
    all_users = um.get_all_users()
    admins = [u for u in all_users if u[2] == "admin"]  # u[2] = role column

    if not admins:
        created = um.register(DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD, role="admin")
        if created:
            print(f"\n[STARTUP]  Default admin created")
            print(f"[STARTUP]    username : {DEFAULT_ADMIN_USERNAME}")
            print(f"[STARTUP]    password : {DEFAULT_ADMIN_PASSWORD}")
            print(f"[STARTUP]    db path  : {DB_PATH}\n")
        else:
            print(f"[STARTUP]    Could not create default admin — username already taken")
    else:
        print(f"[STARTUP] Admin '{admins[0][1]}' already exists — skipping")
        print(f"[CONFIG] GROQ_API_KEY set: {'Yes' if GROQ_API_KEY else 'No'}")

    um.close()
    yield  # server runs here

app = FastAPI(title="Hardware Hub API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = "local-hardware-hub-secret"
ALGORITHM = "HS256"
security = HTTPBearer()

# ─── Auth helpers ───────────────────────────────────────────

def create_token(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "exp": datetime.utcnow() + timedelta(hours=8)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    return decode_token(credentials.credentials)

def require_admin(user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user

# ─── Pydantic models ────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str = "user"

class HardwareItem(BaseModel):
    id: Optional[int] = None
    name: str
    brand: Optional[str] = None
    purchaseDate: Optional[str] = None
    status: Optional[str] = "Available"
    notes: Optional[str] = None

class RentRequest(BaseModel):
    user_id: int
    username: str

# ─── Auth routes ────────────────────────────────────────────

@app.post("/api/auth/login")
def login(req: LoginRequest):
    if not req.email.endswith(".com")or "@" not in req.email:
        raise HTTPException(status_code=400, detail="Invalid format. Please use @domain.com format.")
    um = get_um()
    user = um.login(req.email, req.password)
    um.close()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(user)
    return {"token": token, "user": user}

@app.post("/api/auth/register")
def register(req: RegisterRequest, _=Depends(require_admin)):
    if not req.email.endswith(".com") or "@" not in req.email:
        raise HTTPException(status_code=400, detail="Invalid format. Please use @domain.com format")
    um = get_um()
    result = um.register(req.email, req.password, req.role)
    um.close()
    return {"message": f"User {req.email} created"}

# ─── User routes (admin only) ───────────────────────────────

@app.get("/api/users")
def get_users(_=Depends(require_admin)):
    um = get_um()
    users = um.get_all_users()
    um.close()
    return [{"id": u[0], "username": u[1], "role": u[2]} for u in users]

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, _=Depends(require_admin)):
    um = get_um()
    um.delete_user(user_id)
    um.close()
    return {"message": "Deleted"}

# ─── Hardware routes ────────────────────────────────────────

def row_to_dict(row):
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "brand": row[2],
        "purchaseDate": row[3],
        "status": row[4],
        "notes": row[5],
        "assignedTo": row[6] if len(row) > 6 else None,
    }

@app.get("/api/hardware")
def get_all(_=Depends(get_current_user)):
    hm = get_hm()
    items = hm.get_all()
    hm.close()
    return [row_to_dict(r) for r in items]

@app.get("/api/hardware/my-rentals")
def get_my_rentals(user=Depends(get_current_user)):
    hm = get_hm()
    rows = hm.get_by_assignee(user["username"])
    hm.close()
    return [row_to_dict(r) for r in rows]

@app.get("/api/hardware/{item_id}")
def get_item(item_id: int, _=Depends(get_current_user)):
    hm = get_hm()
    item = hm.get(item_id)
    hm.close()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return row_to_dict(item)

@app.post("/api/hardware")
def add_item(item: HardwareItem, _=Depends(require_admin)):
    hm = get_hm()
    # auto-assign next id if not given
    if item.id is None:
        item.id = hm._get_first_free_id()
    hm.add(item.dict())
    hm.close()
    return {"message": "Added", "id": item.id}

@app.put("/api/hardware/{item_id}")
def update_item(item_id: int, item: HardwareItem, _=Depends(require_admin)):
    hm = get_hm()
    hm.update(item_id, item.dict())
    hm.close()
    return {"message": "Updated"}

@app.delete("/api/hardware/{item_id}")
def delete_item(item_id: int, _=Depends(require_admin)):
    hm = get_hm()
    hm.delete(item_id)
    hm.close()
    return {"message": "Deleted"}

# ─── Rental routes ──────────────────────────────────────────

@app.post("/api/hardware/{item_id}/rent")
def rent_item(item_id: int, req: RentRequest, user=Depends(get_current_user)):
    hm = get_hm()
    item = row_to_dict(hm.get(item_id))
    if not item:
        hm.close()
        raise HTTPException(status_code=404, detail="Item not found")
    if item["status"] != "Available":
        hm.close()
        raise HTTPException(status_code=400, detail=f"Cannot rent — item is '{item['status']}'")
    hm.update(item_id, {
        "name": item["name"],
        "brand": item["brand"],
        "purchaseDate": item["purchaseDate"],
        "status": "In Use",
        "notes": item["notes"],
        "assignedTo": req.username,
    })
    hm.close()
    return {"message": f"Rented to {req.username}"}

@app.post("/api/hardware/{item_id}/return")
def return_item(item_id: int, user=Depends(get_current_user)):
    hm = get_hm()
    item = row_to_dict(hm.get(item_id))
    if not item:
        hm.close()
        raise HTTPException(status_code=404, detail="Item not found")
    if item["status"] != "In Use":
        hm.close()
        raise HTTPException(status_code=400, detail=f"Cannot return — item is '{item['status']}'")
    if item.get("assignedTo") != user.get("username"):
        hm.close()
        raise HTTPException(status_code=403, detail="You can only return items you rented")
    hm.update(item_id, {
        "name": item["name"],
        "brand": item["brand"],
        "purchaseDate": item["purchaseDate"],
        "status": "Available",
        "notes": item["notes"],
        "assignedTo": None,
    })
    hm.close()
    return {"message": "Returned"}

# ─── AI Audit route ─────────────────────────────────────────

@app.get("/api/ai/audit")
async def ai_audit(user=Depends(get_current_user)):
    hm = get_hm()
    items = [row_to_dict(r) for r in hm.get_all()]
    hm.close()

    inventory_json = json.dumps(items, indent=2)

    prompt = f"""You are an IT inventory auditor. Analyze this hardware inventory and flag ALL issues you find.

For each issue provide:
- severity: "critical", "warning", or "info"
- item_id: the ID (or null if general)
- issue: short title
- detail: explanation

Return ONLY a JSON array of issue objects. No markdown, no extra text. You DO NOT need to find issues with every item — only flag items that have potential problems. Be concise.

Inventory:
{inventory_json}"""

    try:
        if not GROQ_API_KEY:
            print("[ERROR] GROQ_API_KEY environment variable is not set")
            raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured")

        print(f"[AI_AUDIT] Making request with model: llama-3.1-8b-instant")
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0
                },
                timeout=30
            )
        
        print(f"[AI_AUDIT] Response status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"[AI_AUDIT] API Error response: {resp.text}")
            raise HTTPException(status_code=resp.status_code, detail=f"Groq API error: {resp.text}")
        
        data = resp.json()
        print(f"[AI_AUDIT] Parsed JSON response keys: {data.keys()}")
        
        raw = data["choices"][0]["message"]["content"]
        print(f"[AI_AUDIT] Raw text from Groq: {raw[:200]}...")
        
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        issues = json.loads(match.group()) if match else []
        print(f"[AI_AUDIT] Successfully parsed {len(issues)} issues")
        return {"issues": issues}
    except json.JSONDecodeError as je:
        print(f"[AI_AUDIT] JSON parse error: {je}")
        print(f"[AI_AUDIT] Failed to parse: {raw}")
        raise HTTPException(status_code=500, detail=f"Failed to parse AI response: {str(je)}")
    except Exception as e:
        print(f"[AI_AUDIT] Exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ─── AI Semantic search ─────────────────────────────────────

class SearchRequest(BaseModel):
    query: str

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")

async def groq_call(client: httpx.AsyncClient, prompt: str, max_tokens: int = 500) -> str:
    """Reusable Groq call — returns raw text content."""
    resp = await client.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": max_tokens,
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


async def search_web(client: httpx.AsyncClient, query: str) -> str:
    """Search Google via Serper API. Returns snippet text."""
    if not SERPER_API_KEY:
        return ""
    resp = await client.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        json={"q": query, "num": 3},
        timeout=10,
    )
    if resp.status_code != 200:
        return ""
    results = resp.json().get("organic", [])

    return " | ".join(r.get("snippet", "")[:300] for r in results[:3])


@app.post("/api/ai/search")
async def ai_search(req: SearchRequest, user=Depends(get_current_user)):
    hm = get_hm()
    items = [row_to_dict(r) for r in hm.get_all()]
    hm.close()

    available = [i for i in items if i["status"] == "Available"]
    if not available:
        return {"results": [], "intent": None, "enriched": False}

    async with httpx.AsyncClient() as client:

        # ── Intent extraction ──────────────────────────
        intent_prompt = f"""Extract the user's hardware search intent as JSON.

User query: "{req.query}"

Return ONLY a JSON object with these fields:
- category: string (e.g. "laptop", "phone", "headphones", "mouse", "tablet", "any")  
- use_case: string (what they want to do with it)
- keywords: array of strings (technical requirements or features)
- search_query: string (a good Google search to find specs for this use case)

Example output:
{{"category": "laptop", "use_case": "video editing", "keywords": ["powerful GPU", "RAM", "fast storage"], "search_query": "best laptop specs for video editing 2024"}}

No markdown, no explanation."""

        intent_raw = await groq_call(client, intent_prompt, max_tokens=200)
        print(f"[AI_SEARCH] Intent raw: {intent_raw}")

        try:
            match = re.search(r'\{.*\}', intent_raw, re.DOTALL)
            intent = json.loads(match.group()) if match else {}
        except Exception:
            intent = {}

        # ── Web enrichment ──
        web_context = ""
        enriched = False

        if SERPER_API_KEY and intent.get("search_query"):
            print(f"[AI_SEARCH] Web search: {intent['search_query']}")
            web_context = await search_web(client, intent["search_query"])
            if web_context:
                enriched = True
                print(f"[AI_SEARCH] Web context: {web_context[:200]}...")

        enriched_items = []
        if SERPER_API_KEY and len(available) <= 15: 
            for item in available:
                spec_query = f"{item['name']} specs review"
                snippet = await search_web(client, spec_query)
                enriched_items.append({**item, "_specs": snippet[:200] if snippet else ""})
        else:
            enriched_items = available

        # ── Matching + ranking ─────────────────────────
        items_for_prompt = json.dumps(enriched_items, indent=2)
        web_section = f"\nAdditional context from web:\n{web_context}\n" if web_context else ""

        match_prompt = f"""You are a hardware advisor. Match the user's need to available inventory items.

User query: "{req.query}"
Detected intent: {json.dumps(intent)}{web_section}

Available inventory:
{items_for_prompt}

Return ONLY a JSON array of matches, best first, max 5 results:
[{{"id": 1, "score": 0.9, "reason": "short reason why this fits"}}]

Only include items that genuinely match. If nothing fits, return [].
No markdown, no explanation."""

        match_raw = await groq_call(client, match_prompt, max_tokens=400)
        print(f"[AI_SEARCH] Match raw: {match_raw}")

        try:
            arr_match = re.search(r'\[.*\]', match_raw, re.DOTALL)
            matches = json.loads(arr_match.group()) if arr_match else []
        except Exception:
            matches = []

    id_to_item = {i["id"]: i for i in items}
    results = []
    for m in matches:
        item = id_to_item.get(m.get("id"))
        if item:
            results.append({
                **item,
                "_score": m.get("score", 0),
                "_reason": m.get("reason", ""),
            })

    print(f"[AI_SEARCH] Final results: {len(results)} items")
    return {
        "results": results,
        "intent": intent,
        "enriched": enriched,
    }
# ─── Seed endpoint ──────────────────────────────────────────

@app.post("/api/seed")
def seed_db():
    """Load initial seed data. Run once."""
    import json, os
    seed_path = os.path.join(os.path.dirname(__file__), "seed.json")
    if not os.path.exists(seed_path):
        raise HTTPException(status_code=404, detail="seed.json not found")
    with open(seed_path) as f:
        items = json.load(f)

    hm = get_hm()
    for item in items:
        hm.add(item)
    hm.close()

    # create default admin
    um = get_um()
    um.register("admin@local.com", "admin123", role="admin")
    um.close()

    return {"message": f"Seeded {len(items)} items + admin user"}
