from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import os
import requests

app = FastAPI()

# -------------------------
# STATIC FILES
# -------------------------
# /public -> за index.html, favicon, sitemap и т.н.
app.mount("/public", StaticFiles(directory="public"), name="public")


# -------------------------
# HOME PAGE
# -------------------------
@app.get("/")
async def home():
    return FileResponse("public/index.html")


# -------------------------
# GOOGLE SITE VERIFY
# (ако не ти трябва – можеш да го махнеш)
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
    # ако смениш домейна – смени и линка долу
    return PlainTextResponse(
        "User-agent: *\n"
        "Allow: /\n"
        "Sitemap: https://tryrealtyai.com/sitemap.xml\n",
        media_type="text/plain",
    )


# -------------------------
# ENV KEYS
# -------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# =====================================================
#  SAFE SANITIZER – чисти емоджита/маркап
# =====================================================
def sanitize_text(raw: str) -> str:
    if not raw:
        return ""

    text = raw

    # махаме markdown символите
    for md in ["**", "*", "#", "`", "_"]:
        text = text.replace(md, "")

    # махаме emoji, оставяме $, %, цифри и т.н.
    def keep(ch):
        code = ord(ch)
        if 0x1F000 <= code <= 0x1FAFF:
            return False
        if 0x2600 <= code <= 0x27BF:
            return False
        return True

    text = "".join(ch for ch in text if keep(ch))

    # нормализираме празните редове
    lines = [ln.rstrip() for ln in text.split("\n")]
    clean_lines = []
    skip_empty = False
    for l in lines:
        if l.strip() == "":
            if not skip_empty:
                clean_lines.append("")
            skip_empty = True
        else:
            clean_lines.append(l)
            skip_empty = False

    final = "\n".join(clean_lines).strip()
    return final


# =====================================================
#  /analyze – основният AI анализ (всички са "PRO")
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

    if not OPENAI_API_KEY:
        return JSONResponse(
            {"result": "Server error: OPENAI_API_KEY is not configured."}
        )

    model = "gpt-4o"

    prompt = f"""
You are an expert real estate analyst.
Generate a long structured investment report in clear English.

Use exactly these sections, in this order:

Rental Yield:
Monthly Cashflow:
Annual Cashflow:
ROI (5-year & 10-year):
Cap Rate:
Risk Score (1–100):
Market Summary:
Final Recommendation:

RULES:
- Always use digits for numbers (8.5%, $12400), never words.
- No markdown, no bullet lists.
- Each section must be 2–5 sentences, separated by normal line breaks.
- Do not invent extra sections.

INPUT DATA:
Price: {price}
Monthly Rent: {rent}
Monthly Expenses: {expenses}
Property Taxes: {taxes}
Location: {location}
    """.strip()

    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.post(
            url,
            headers=headers,
            json={
                "model": model,
                "input": prompt,
            },
            timeout=60,
        )
        data = r.json()
        # новият Responses API
        text = data["output"][0]["content"][0]["text"]
    except Exception as e:
        text = f"AI error: {e}"

    clean = sanitize_text(text)
    return JSONResponse({"result": clean})


# -------------------------
# START (локално)
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=port)
