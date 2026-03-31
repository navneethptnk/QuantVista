# QuantVista

QuantVista is set up to run on Vercel without changing the app’s core Flask visualization logic.

## Local development

1. Create and activate a virtual environment.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Run the Flask app:

```powershell
python app.py
```

4. Open `http://127.0.0.1:5000`.

## Vercel deployment

This repo includes:

- `api/index.py` as the Vercel Python entrypoint
- `vercel.json` to route requests into the Flask app
- serverless-friendly storage defaults in `app.py`
- a static frontend in `docs/` that Vercel serves through the Flask app

### Important note

The visualization and analysis flow is now stateless-capable. The browser can send the uploaded file contents back with each analysis or chart request, which avoids depending on permanent server disk storage in Vercel.

Saved dashboards are stored in browser `localStorage`, so they work on Vercel without needing a database.

### Deploy steps

1. Import the repo into Vercel.
2. Ensure Vercel detects it as a Python project.
3. Deploy with the existing `requirements.txt`.
4. Open the deployed URL and use the app normally.

### Optional environment variable

If you later host the frontend on a different origin, you can allow cross-origin requests with:

```text
QUANTVISTA_ALLOWED_ORIGINS=https://your-frontend-domain.example
```

If you do not need cross-origin access, you can skip this.

## Project structure

- `app.py`: main Flask app
- `api/index.py`: Vercel function entrypoint
- `docs/`: frontend assets used by the app
- `docs/config.js`: optional runtime frontend config
