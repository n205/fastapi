from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import numpy as np

app = FastAPI()

# Staticファイルとテンプレート設定
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# トップページ
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ランキングAPI
@app.get('/api/rank', response_class=HTMLResponse)
async def rank(q1: int = 0, q2: int = 0, q3: int = 0):
    user = np.array([q1, q2, q3])
    company_data = [
        {'Company': 'A社', 'Value': '本質と静けさを重視', 'Vector': np.array([-1, -2, -2]), 'URL': 'https://example.com/a'},
        {'Company': 'B社', 'Value': 'スピードと活気', 'Vector': np.array([1, 2, 2]), 'URL': 'https://example.com/b'},
        {'Company': 'C社', 'Value': 'バランス重視', 'Vector': np.array([0, 0, 0]), 'URL': 'https://example.com/c'},
    ]

    def score(u, v): return 1 / (1 + np.linalg.norm(u - v))

    for c in company_data:
        c['Score'] = round(score(user, c['Vector']), 3)

    # スコア順でソート
    sorted_data = sorted(company_data, key=lambda x: x['Score'], reverse=True)

    # HTMLテーブルを生成
    html = '<table border="1" cellspacing="0" cellpadding="6">'
    html += '<tr><th>企業名</th><th>価値観</th><th>スコア</th><th>リンク</th></tr>'

    for c in sorted_data:
        html += f"<tr><td>{c['Company']}</td><td>{c['Value']}</td><td>{c['Score']}</td><td><a href='{c['URL']}' target='_blank'>🔗</a></td></tr>"

    html += '</table>'
    return html
    

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8080)

