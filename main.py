from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
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
async def rank(q1: int = 4, q2: int = 4, q3: int = 4):
    # ユーザー入力（1〜7）
    user = np.array([q1, q2, q3])

    # ダミーの企業データ（1〜7スケール）
    company_data = [
        {'Company': 'A社', 'Value': '自己方向性・安全志向', 'Vector': np.array([6, 7, 2]), 'URL': 'https://example.com/a'},
        {'Company': 'B社', 'Value': '普遍主義・安全志向', 'Vector': np.array([3, 6, 6]), 'URL': 'https://example.com/b'},
        {'Company': 'C社', 'Value': '自由・変化志向', 'Vector': np.array([7, 2, 1]), 'URL': 'https://example.com/c'},
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
