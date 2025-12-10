from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import os
import uvicorn
import requests
from io import BytesIO
from textwrap import wrap
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor
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
# ROBOTS.TXT
# -------------------------
@app.get("/robots.txt")
async def robots():
    return PlainTextResponse(
        "User-agent: *\n"
        "Allow: /\n"
        "Sitemap: https://tryrealtyai.com/sitemap.xml\n",
        media_type="text/plain"
    )


# -------------------------
# ENV KEYS
# -------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# =====================================================
# CLEAN SANITIZER
# =====================================================
def sanitize_text(raw: str) -> str:
    if not raw:
        return ""

    text = raw

    # Remove markdown
    for md in ["**", "*", "#", "`", "_"]:
        text = text.replace(md, "")

    # Remove emoji only
    def keep(ch):
        code = ord(ch)
        if 0x1F000 <= code <= 0x1FAFF: return False
        if 0x2600 <= code <= 0x27BF: return False
        return True

    text = "".join(ch for ch in text if keep(ch))

    # Normalize blank lines
    lines = [ln.rstrip() for ln in text.split("\n")]
    clean = []
    skip = False
    for l in lines:
        if l.strip() == "":
            if not skip:
                clean.append("")
            skip = True
        else:
            clean.append(l)
            skip = False

    return "\n".join(clean).strip()


# =====================================================
# AI ANALYSIS — GPT-4o ALWAYS
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

    prompt = f"""
You are an expert real estate analyst.
Generate a clean structured report in this order:

Rental Yield:
Monthly Cashflow:
Annual Cashflow:
ROI (5-year & 10-year):
Cap Rate:
Risk Score (1–100):
Market Summary:
Final Recommendation:

Rules:
- Use only digits (8.5%, $12,400)
- No markdown, no lists
- Clean English paragraphs

INPUT:
Price: {price}
Rent: {rent}
Expenses: {expenses}
Taxes: {taxes}
Location: {location}
"""

    url = "https://api.openai.com/v1/responses"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

    try:
        r = requests.post(url, headers=headers, json={"model": "gpt-4o", "input": prompt}, timeout=60)
        text = r.json()["output"][0]["content"][0]["text"]
    except Exception as e:
        return JSONResponse({"result": f"AI error: {e}"})

    clean = sanitize_text(text)
    return JSONResponse({"result": clean})


# =====================================================
# PDF SECTION SPLITTER
# =====================================================
def split_sections_for_pdf(text):
    titles = [
        "Rental Yield",
        "Monthly Cashflow",
        "Annual Cashflow",
        "ROI (5-year & 10-year)",
        "Cap Rate",
        "Risk Score",
        "Market Summary",
        "Final Recommendation",
    ]

    pattern = "(" + "|".join(re.escape(t) for t in titles) + "):"
    matches = list(re.finditer(pattern, text))

    if not matches:
        return [("Report", text)]

    out = []
    for i, m in enumerate(matches):
        title = m.group(1)
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        body = text[start:end].strip()
        out.append((title, body))

    return out


# =====================================================
# MODERN PROFESSIONAL PDF ENGINE
# =====================================================
@app.post("/generate_pdf")
async def generate_pdf(request: Request):
    text = sanitize_text((await request.json())["text"])
    sections = split_sections_for_pdf(text)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    accent = HexColor("#7B3FF2")  # Purple accent
    black = HexColor("#000000")

    # ---------------------------------------------------
    # COVER PAGE
    # ---------------------------------------------------
    try:
        logo_path = "public/favicon.png"
        if os.path.exists(logo_path):
            img = ImageReader(logo_path)
            pdf.drawImage(img, width/2 - 50, height - 200, width=100, height=100, mask="auto")
    except:
        pass

    pdf.setFont("Helvetica-Bold", 28)
    pdf.drawCentredString(width/2, height - 260, "RealtyAI Investment Report")

    pdf.setFont("Helvetica", 14)
    pdf.drawCentredString(width/2, height - 290, "AI-powered real estate analysis")

    pdf.showPage()

    # ---------------------------------------------------
    # MAIN CONTENT
    # ---------------------------------------------------
    left = 50
    y = 760
    line_height = 15
    bottom_margin = 70

    def page_footer():
        pdf.setFont("Helvetica-Oblique", 9)
        pdf.drawCentredString(width/2, 35, "RealtyAI • tryrealtyai.com")

    def new_page():
        nonlocal y
        page_footer()
        pdf.showPage()
        pdf.setFont("Helvetica", 11)
        y = 760

    for title, body in sections:

        wrapped = []
        for ln in body.split("\n"):
            wrapped.extend(wrap(ln, 90) or [""])

        # Height required for this whole section
        needed = (len(wrapped) + 3) * line_height

        # If not enough space → new page BEFORE title
        if y - needed < bottom_margin:
            new_page()

        # TITLE
        pdf.setFont("Helvetica-Bold", 14)
        pdf.setFillColor(accent)
        pdf.drawString(left, y, f"■ {title}")
        y -= 22

        # BODY
        pdf.setFont("Helvetica", 11)
        pdf.setFillColor(black)

        for ln in wrapped:
            if y - line_height < bottom_margin:
                new_page()
                # redraw title header on the new page? NO — we continue section naturally
            pdf.drawString(left, y, ln)
            y -= line_height

        y -= 12  # extra space after section

    # LAST PAGE FOOTER
    page_footer()
    pdf.showPage()

    pdf.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=RealtyAI_Report.pdf"}
    )


# -------------------------
# START SERVER
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)

