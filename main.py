from fastapi import FastAPI, Request, Form, Query, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx
import os
import stripe

import numpy as np
import pandas as pd
import gspread
from google.oauth2 import service_account
from gspread_dataframe import get_as_dataframe
import logging
import random

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from reportlab.pdfgen import canvas
from io import BytesIO

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

stripe_api_key = os.getenv('STRIPE_SECRET_KEY')
stripe_webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')

if not stripe_api_key or not stripe_webhook_secret:
    print("⚠️ Stripeのキーが設定されていません")
    # RuntimeErrorは起動時に投げない
else:
    print("✅ Stripeキー読み込み成功")
    stripe.api_key = stripe_api_key

ip_cache = {}

async def get_location_from_ip(ip: str):
    if ip in ip_cache:
        return ip_cache[ip]
    try:
        async with httpx.AsyncClient() as client:
            url = f'https://ipinfo.io/{ip}/json'
            response = await client.get(url, timeout=5)
            data = response.json()
            result = {
                'ip': ip,
                'city': data.get('city', ''),
                'region': data.get('region', ''),
                'country': data.get('country', ''),
                'org': data.get('org', ''),
            }
            ip_cache[ip] = result
            return result
    except Exception as e:
        return {'ip': ip, 'error': str(e)}

PVQ_QUESTIONS = [
    {"text": "自分で考え、自分のやり方で仕事を進めることを重視している", "axis": "PVQ_自己方向性"},
    {"text": "運営が安定していて、予測できる状況を重視している", "axis": "PVQ_安全"},
    {"text": "多様性や公平さ、人権などを重視している", "axis": "PVQ_普遍主義"},
    {"text": "新しい挑戦や変化を求めることを重視している", "axis": "PVQ_刺激"},
    {"text": "権力や地位、名声を得ることを重視している", "axis": "PVQ_権力"},
    {"text": "成功や達成、優秀さを重視している", "axis": "PVQ_達成"},
    {"text": "快楽や楽しさ、幸福感を重視している", "axis": "PVQ_快楽"},
]

def load_company_data():
    SPREADSHEET_ID = '18Sb4CcAE5JPFeufHG97tLZz9Uj_TvSGklVQQhoFF28w'
    WORKSHEET_NAME = 'バリュー抽出'

    try:
        creds = service_account.Credentials.from_service_account_file(
            '/secrets/service-account-json',
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        df = get_as_dataframe(worksheet)
        df.fillna('', inplace=True)

        df = df[
            (df['会社名'] != '') &
            (df['会社名'] != '対象外') &
            (df['PVQ_自己方向性'] != '') &
            (df['PVQ_安全'] != '') &
            (df['PVQ_普遍主義'] != '') &
            (df['色1コード'] != '') &
            (df['色2コード'] != '')
        ]

        for axis in ['PVQ_自己方向性', 'PVQ_安全', 'PVQ_普遍主義']:
            df[axis] = pd.to_numeric(df[axis], errors='coerce')

        df = df.dropna(subset=['PVQ_自己方向性', 'PVQ_安全', 'PVQ_普遍主義'])

        return df

    except Exception as e:
        logging.error('❌ スプレッドシート読み込み失敗:', exc_info=True)
        return pd.DataFrame()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    forwarded_for = request.headers.get('x-forwarded-for', '')
    ip = forwarded_for.split(',')[0] if forwarded_for else request.client.host
    location = await get_location_from_ip(ip)

    # ✅ トップページではランダム3問だけ
    selected_questions = random.sample(PVQ_QUESTIONS, 3)

    return templates.TemplateResponse("index.html", {
        'request': request,
        'user_region': location.get('region', '不明'),
        'questions': selected_questions
    })

@app.get("/api/questions")
async def get_questions(count: int = Query(None)):
    """
    count 指定があればランダムにその件数だけ返す。
    指定がなければ全件返す。
    """
    if count is not None and count > 0:
        selected_questions = random.sample(PVQ_QUESTIONS, min(count, len(PVQ_QUESTIONS)))
    else:
        selected_questions = PVQ_QUESTIONS
    return JSONResponse(content={"questions": selected_questions})

@app.get("/desc_answer", response_class=HTMLResponse)
async def desc_answer(request: Request):
    return templates.TemplateResponse("desc_answer.html", {"request": request})

@app.post("/api/rank", response_class=HTMLResponse)
async def rank(
    axis1: str = Form(...), q1: int = Form(...),
    axis2: str = Form(...), q2: int = Form(...),
    axis3: str = Form(...), q3: int = Form(...)
):
    user_vector = {
        axis1: q1,
        axis2: q2,
        axis3: q3
    }

    df = load_company_data()
    if df.empty:
        return HTMLResponse('<p>データ取得に失敗しました</p>', status_code=500)

    def compute_score(row):
        score = 0
        for axis, val in user_vector.items():
            if axis in row:
                score += (val - row[axis]) ** 2
        return 1 / (1 + np.sqrt(score))

    df['スコア'] = df.apply(compute_score, axis=1)
    df = df.sort_values('スコア', ascending=False).head(3)

    table_html = '<div id="table-view" class="table-wrapper"><table>'
    table_html += (
        '<thead><tr>'
        '<th>会社名 (リンク)</th><th>色傾向</th><th>価値観</th><th>スコア</th>'
        '</tr></thead><tbody>'
    )
    for _, row in df.iterrows():
        name_link = f"<a href='{row['URL']}' target='_blank'>{row['会社名']}</a>"
        color_block = (
            f"<div class='color-block'>"
            f"<div class='half' style='background-color: {row['色1コード']};'></div>"
            f"<div class='half' style='background-color: {row['色2コード']};'></div>"
            f"</div>"
        )
        table_html += (
            f"<tr><td>{name_link}</td>"
            f"<td class='color-column'>{color_block}</td>"
            f"<td><div class='clamp'>{row['バリュー']}</div></td>"
            f"<td>{round(row['スコア'], 3)}</td></tr>"
        )
    table_html += '</tbody></table></div>'

    card_html = '<div id="card-view">'
    for _, row in df.iterrows():
        name_link = f"<a href='{row['URL']}' target='_blank'>{row['会社名']}</a>"
        color_block = (
            f"<div class='color-block'>"
            f"<div class='half' style='background-color: {row['色1コード']};'></div>"
            f"<div class='half' style='background-color: {row['色2コード']};'></div>"
            f"</div>"
        )
        card_html += (
            f"<div class='card'>"
            f"<h3>{name_link}</h3>"
            f"{color_block}"
            f"<div class='value'>{row['バリュー']}</div>"
            f"<div class='score'>スコア: {round(row['スコア'], 3)}</div>"
            f"</div>"
        )
    card_html += '</div>'

    return HTMLResponse(table_html + card_html)

@app.post("/create-checkout-session")
async def create_checkout_session():
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'jpy',
                    'product_data': {
                        'name': '診断結果ページアクセス'
                    },
                    'unit_amount': 20,  # 金額(例: 1000円)
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url='https://fastapi-232873166322.asia-northeast1.run.app/success',
            cancel_url='https://fastapi-232873166322.asia-northeast1.run.app/cancel',
        )
        return JSONResponse(content={'url': checkout_session.url})
    except Exception as e:
        return JSONResponse(content={'error': str(e)}, status_code=400)

@app.post("/stripe/webhook")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, stripe_webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        return JSONResponse(status_code=400, content={"error": "Invalid signature"})

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        # ユーザーのメールアドレスを取得
        customer_email = session.get("customer_details", {}).get("email")
        if customer_email:
            # PDF生成 & メール送信をバックグラウンドで実行
            pdf_bytes = generate_pdf("ご購入ありがとうございました。こちらがレポートです。")
            background_tasks.add_task(
                send_email_with_pdf,
                to_email=customer_email,
                subject="ご購入レポート",
                body="ご購入いただきありがとうございます。PDFレポートを添付いたします。",
                pdf_bytes=pdf_bytes,
                filename="report.pdf"
            )

    return JSONResponse(status_code=200, content={"status": "success"})

# PDF生成関数
def generate_pdf(content: str) -> bytes:
    buffer = BytesIO()
    p = canvas.Canvas(buffer)
    p.drawString(100, 750, content)
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer.read()

# メール送信関数
def send_email_with_pdf(to_email: str, subject: str, body: str, pdf_bytes: bytes, filename: str):
    from_email = os.getenv("SMTP_FROM")
    password = os.getenv("SMTP_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))

    # メール作成
    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    # PDF添付
    part = MIMEApplication(pdf_bytes, Name=filename)
    part["Content-Disposition"] = f'attachment; filename="{filename}"'
    msg.attach(part)

    # SMTP送信
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(from_email, password)
        server.send_message(msg)
        
@app.get("/success")
async def success(request: Request):
    return templates.TemplateResponse("success.html", {"request": request})

@app.get("/cancel")
async def cancel(request: Request):
    return templates.TemplateResponse("cancel.html", {"request": request})

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8080)
