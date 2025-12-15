# ベースイメージ
FROM python:3.9-slim

# 作業ディレクトリ設定
WORKDIR /app

# 依存関係ファイルのコピーとインストール
# キャッシュを効かせるために先にrequirementsだけコピーします
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ソースコードをコピー
COPY . .

# Streamlitのデフォルトポート
EXPOSE 8501

# ヘルスチェック（本番運用などで役立ちます）
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

# アプリ起動コマンド
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]