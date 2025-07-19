from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx

import numpy as np
import pandas as pd
import gspread
from google.oauth2 import service_account
from gspread_dataframe import get_as_dataframe
import logging

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# IPキャッシュ
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

# Google Sheetsからデータを取得
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
            (df['会社名G'] != '') &
            (df['会社名G'] != '対象外') &
            (df['PVQ_自己方向性'] != '') &
            (df['PVQ_安全'] != '') &
            (df['PVQ_普遍主義'] != '') &
            (df['色1コード'] != '') &
            (df['色2コード'] != '')
        ]

        df['PVQ_自己方向性'] = pd.to_numeric(df['PVQ_自己方向性'], errors='coerce')
        df['PVQ_安全'] = pd.to_numeric(df['PVQ_安全'], errors='coerce')
        df['PVQ_普遍主義'] = pd.to_numeric(df['PVQ_普遍主義'], errors='coerce')
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
    print(f"📍 アクセス元: {location}")

    return templates.TemplateResponse("index.html", {
        'request': request,
        'user_region': location.get('region', '不明')
    })

@app.get("/api/rank", response_class=HTMLResponse)
async def rank(q1: int = 4, q2: int = 4, q3: int = 4):
    user_vector = np.array([q1, q2, q3])
    df = load_company_data()
    if df.empty:
        return HTMLResponse('<p>データ取得に失敗しました</p>', status_code=500)

    def compute_score(row):
        vec = np.array([
            row['PVQ_自己方向性'],
            row['PVQ_安全'],
            row['PVQ_普遍主義']
        ])
        return 1 / (1 + np.linalg.norm(user_vector - vec))

    df['スコア'] = df.apply(compute_score, axis=1)
    df = df.sort_values('スコア', ascending=False).head(3)

    html = '<table border="1" cellspacing="0" cellpadding="6">'
    html += (
        '<thead>'
        '<tr>'
        '<th rowspan="2">会社名 (リンク)</th>'
        '<th colspan="2">色傾向</th>'
        '<th rowspan="2">価値観</th>'
        '<th rowspan="2">スコア</th>'
        '</tr>'
        '<tr>'
        '<th>色1</th>'
        '<th>色2</th>'
        '</tr>'
        '</thead>'
        '<tbody>'
    )
    
    for _, row in df.iterrows():
        name_link = f"<a href='{row['URL']}' target='_blank'>{row['会社名G']}</a>"
        html += (
            f"<tr>"
            f"<td>{name_link}</td>"
            f"<td style='background-color: {row['色1コード']};'></td>"
            f"<td style='background-color: {row['色2コード']};'></td>"
            f"<td><div class='clamp'>{row['バリューT']}</div></td>"
            f"<td>{round(row['スコア'], 3)}</td>"
            f"</tr>"
        )
    
    html += '</tbody></table>'

    return html

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8080)
