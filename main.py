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
@app.get('/api/rank', response_class=PlainTextResponse)
async def rank(q1: int = 0, q2: int = 0, q3: int = 0):
    user = np.array([q1, q2, q3])
    company_data = [
        {'Company': 'A社', 'Value': '本質と静けさを重視', 'Vector': np.array([-1, -2, -2]), 'URL': 'https://example.com/a'},
        {'Company': 'B社', 'Value': 'スピードと活気', 'Vector': np.array([1, 2, 2]), 'URL': 'https://example.com/b'},
        {'Company': 'C社', 'Value': 'バランス重視', 'Vector': np.array([0, 0, 0]), 'URL': 'https://example.com/c'},
    ]

    def score(u, v): return 1 / (1 + np.linalg.norm(u - v))

    result = ''
    for c in company_data:
        s = round(score(user, c['Vector']), 3)
        result += f"{c['Company']}: {s}（{c['Value']}）<br>"

    return result

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8080)

