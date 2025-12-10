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
import re

app = FastAPI()

# Serve static folder
app.mount("/public", StaticFiles(directory="public"), name="public")


@app.get("/")
async def home():
    return FileResponse("public/index.html")


# Google Search Console verification
@app.get("/googlec02c838b73c409da.html")
async def google_verify():
    return PlainTextResponse("google-site-verification: googlec02c838b73c409da.html")


# Sitemap
@app.get("/sitemap.xml")
async def sitemap():
    return FileResponse("public/sitemap.xml", media_type="application/xml")


# Robots.txt
@app.get("/robots.txt")
async def robots():
    return PlainTextResponse(
        "User-agent: *\n"
        "Allow: /\n"
        "Sitemap: https://tryrealtyai.com/sitemap.xml\n",
        media_type="text/plain"
    )


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# TEXT SANITIZER
def sanitize_text(raw: str) -> str:
    if not raw:
        return ""

    text = raw

    # Remove markdown, keep numbers
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

    # Clean blank lines
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


# AI ANALYSIS
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
Generate a long structured report with clear English paragraphs.
Sections (in this exact order):
Rental Yield:
Monthly Cashflow:
Annual Cashflow:
ROI (5-year & 10-year):
Cap Rate:
Risk Score (1–100):
Market Summary:
Final Recommendation:

RULES:
- Use digits only (8.5%, $12,400)
- NEVER spell numbers as words (“twelve thousand”)
- No markdown, no bullets
- Clean paragraphs only

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
        r = requests.post(url, headers=headers, json={"model": "gpt-4o", "input": prompt}, timeout=60)
        text = r.json()["output"][0]["content"][0]["text"]
    except Exception as e:
        text = f"AI error: {e}"

    return JSONResponse({"result": sanitize_text(text)})


# SPLIT INTO PDF SECTIONS
def split_sections(text):
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
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        out.append((title, body))

    return out


# ADVANCED PDF GENERATOR — WITH PAGE BREAKS FIXED
@app.post("/generate_pdf")
async def generate_pdf(request: Request):
    text = sanitize_text((await request.json())["text"])
    sections = split_sections(text)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # COVER PAGE
    try:
        logo_path = "public/favicon.png"
        if os.path.exists(logo_path):
            pdf.drawImage(logo_path, width / 2 - 40, height - 160, width=80, height=80)
    except:
        pass

    pdf.setFont("Helvetica-Bold", 28)
    pdf.drawCentredString(width / 2, height - 250, "RealtyAI Investment Report")

    pdf.setFont("Helvetica", 14)
    pdf.drawCentredString(width / 2, height - 280, "AI-powered real estate analysis")

    pdf.showPage()

    # MAIN CONTENT
    left = 50
    y = 760
    line_h = 16
    bottom_margin = 70

    def new_page():
        nonlocal y
        pdf.setFont("Helvetica-Oblique", 9)
        pdf.drawCentredString(width / 2, 40, "RealtyAI • tryrealtyai.com")
        pdf.showPage()
        y = 760

    for title, body in sections:

        # Draw title (never split across pages)
        wrapped = []
        for line in body.split("\n"):
            wrapped.extend(wrap(line, 90))

        needed_space = (len(wrapped) + 3) * line_h

        if y - needed_space < bottom_margin:
            new_page()

        # Title
        pdf.setFont("Helvetica-Bold", 16)
        pdf.setFillColorRGB(0.45, 0.15, 0.85)
        pdf.drawString(left, y, f"■ {title}")
        y -= 26

        # Body text
        pdf.setFont("Helvetica", 11)
        pdf.setFillColorRGB(0, 0, 0)

        for line in wrapped:
            if y < bottom_margin:
                new_page()
                pdf.setFont("Helvetica", 11)

            pdf.drawString(left, y, line)
            y -= line_h

        y -= 12

    pdf.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=RealtyAI_Report.pdf"}
    )


# START SERVER (Render)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
