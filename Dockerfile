# Pythonの軽量ベースイメージ
FROM python:3.10-slim

# 作業ディレクトリ
WORKDIR /app

# ファイルコピー
COPY . .

# 必要パッケージのインストール
RUN pip install --no-cache-dir -r requirements.txt

# Cloud Runで使うポート番号
ENV PORT 8080

# ポートを明示（念のため）
EXPOSE 8080

# uvicornでアプリを起動
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
