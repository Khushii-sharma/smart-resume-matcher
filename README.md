# Smart Resume Matcher

A Streamlit app that compares a PDF resume with a job description using the
Gemini API.

## Deploy publicly with Streamlit Community Cloud

1. Push this repository to GitHub.
2. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) and
   create an app from `Khushii-sharma/smart-resume-matcher`.
3. Select the `main` branch and `app.py` as the main file.
4. In the app's **Settings → Secrets**, add your Gemini API key:

   ```toml
   GEMINI_API_KEY = "your-gemini-api-key"
   ```

5. Deploy the app. Streamlit Cloud installs the dependencies from
   `requirements.txt` and provides a public app URL.

Keep the API key in Streamlit Cloud Secrets; do not commit it to GitHub. For
local development, create a `.env` file in the repository root containing
`GEMINI_API_KEY=your-gemini-api-key`.

## Run locally

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```
