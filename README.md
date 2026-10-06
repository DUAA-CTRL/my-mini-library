# My Mini Library — phone friendly + live ready

Flask + MongoDB Atlas + GridFS + Ollama.

## What was fixed

- PDFs are stored in MongoDB Atlas GridFS, so the same PDF can be opened from another phone/laptop using the same live website.
- Added a dedicated mobile PDF reader at `/read/<id>`.
- Added browser-inline PDF viewing at `/pdf/<id>`.
- Added a real download route at `/download/<id>`.
- Added a Share button on the PDF reader. On supported phones it uses the phone's share sheet; otherwise it copies the PDF link.
- Mobile layout, buttons, forms and book cards are responsive.
- Uploads are limited to 50 MB by default.
- Added Gunicorn + Render configuration for production.
- Local Ollama and Ollama Cloud are selected through environment variables.
- Secrets are not included in this ZIP. Use `.env.example` locally and Render Environment Variables for deployment.

## Local run

1. Copy `.env.example` to `.env`.
2. Put your MongoDB Atlas URI in `.env`.
3. Start local Ollama and make sure `llama3.2:latest` exists.
4. Run:

```cmd
pip install -r requirements.txt
python app.py
```

5. Open `http://127.0.0.1:5000`.

## Live on Render

Push this project to GitHub, then create a Render Web Service from the repository.

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
gunicorn --bind 0.0.0.0:$PORT app:app
```

Set these Render Environment Variables:

- `MONGO_URI` = your MongoDB Atlas connection string
- `MONGO_DB` = `my_library`
- `SECRET_KEY` = a strong random value (or let render.yaml generate it)
- `OLLAMA_URL` = `https://ollama.com`
- `OLLAMA_API_KEY` = your Ollama Cloud API key
- `OLLAMA_MODEL` = a model available to your Ollama account, for example `gpt-oss:20b`

Do NOT put MongoDB or Ollama secrets into `render.yaml` or GitHub.

Once Render gives you a public `https://...onrender.com` URL, open that same URL on your phone. Uploading a PDF there stores it in MongoDB Atlas, and another phone opening the same live URL will see it in the library.

