from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import os
import uvicorn
import requests
import re

app = FastAPI()

# -------------------------
# STATIC FILES
# -------------------------
app.mount("/public", StaticFiles(directory="public"), name="public")


@app.get("/")
async def home():
    return FileResponse("public/index.html")


# -------------------------
# GOOGLE VERIFY
# -------------------------
@app.get("/googlec02c838b73c409da.html")
async def google_verify():
    return PlainTextResponse("google-site-verification: googlec02c838b73c409da.html")


# -------------------------
# SITEMAP
# -------------------------
@app.get("/sitemap.xml")
async def sitemap():
    return FileResponse("public/sitemap.xml", media_type="application/xml")


# -------------------------
# ROBOTS
# -------------------------
@app.get("/robots.txt")
async def robots():
    return PlainTextResponse(
        "User-agent: *\nAllow: /\nSitemap: https://tryrealtyai.com/sitemap.xml\n",
        media_type="text/plain",
    )


# -------------------------
# ENV KEYS
# -------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# =====================================================
# SANITIZER
# =====================================================
def sanitize_text(raw: str) -> str:
    if not raw:
        return ""

    text = raw

    # Remove markdown indicators
    for md in ["**", "*", "#", "`", "_"]:
        text = text.replace(md, "")

    # Remove emojis only
    def keep(ch):
        code = ord(ch)
        if 0x1F000 <= code <= 0x1FAFF:
            return False
        if 0x2600 <= code <= 0x27BF:
            return False
        return True

    text = "".join(ch for ch in text if keep(ch))

    # Normalize spacing
    lines = [ln.rstrip() for ln in text.split("\n")]
    cleaned = []
    skip = False
    for l in lines:
        if l.strip() == "":
            if not skip:
                cleaned.append("")
            skip = True
        else:
            cleaned.append(l)
            skip = False

    return "\n".join(cleaned).strip()


# =====================================================
# AI ANALYSIS — ALWAYS GPT-4o
# =====================================================
@app.post("/analyze")
async def analyze_property(request: Request):
    data = await request.json()

    price = data.get("price")
    rent = data.get("rent")
    expenses = data.get("expenses")
    taxes = data.get("taxes")
    location = data.get("location")

    if not price or not rent or not location:
        return JSONResponse({"result": "Please fill Price, Rent and Location."})

    model = "gpt-4o"

    prompt = f"""
You are an expert real estate analyst.
Generate a long, structured report in clean English paragraphs.
Sections (in this order):
Rental Yield:
Monthly Cashflow:
Annual Cashflow:
ROI (5-year & 10-year):
Cap Rate:
Risk Score (1–100):
Market Summary:
Final Recommendation:

RULES:
- Use digits, not words (8.5%, $12,400)
- No markdown or bullets
- Clean text only

INPUT:
Price: {price}
Rent: {rent}
Expenses: {expenses}
Taxes: {taxes}
Location: {location}
"""

    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        r = requests.post(url, headers=headers, json={"model": model, "input": prompt}, timeout=60)
        text = r.json()["output"][0]["content"][0]["text"]
    except Exception as e:
        text = f"AI error: {e}"

    clean = sanitize_text(text)
    return JSONResponse({"result": clean})


# -------------------------
# START SERVER
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
