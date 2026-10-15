# Assignment Tracker — Streamlit

A simple assignment tracker implemented with Streamlit.

Run locally:
1. Create and activate a virtualenv (recommended)
2. pip install -r requirements.txt
3. streamlit run streamlit_app.py

Deploy to Streamlit Community Cloud:
1. Push this repository to GitHub.
2. Visit https://share.streamlit.io and sign in.
3. Create a new app, connect your GitHub repo, choose the branch (e.g., main) and the main file `streamlit_app.py`.
4. Deploy. The app will be live on a streamlit.app domain.

Persistence:
- The app writes to `data.json` in the app directory. That file persists while the Streamlit instance remains running, but it can be lost on redeploys or instance restarts. For durable storage use a dedicated DB (Supabase, Postgres, Google Sheets, etc.).