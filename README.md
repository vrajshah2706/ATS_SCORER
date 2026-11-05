# ATS Resume Scorer

AI-powered resume analyser: upload a resume (PDF/DOCX), optionally add a job description, and get an ATS score out of 100, prioritised feedback, skill validation, and a downloadable PDF report.

- **Live frontend:** https://atsscorer-vraj.streamlit.app
- **Full project write-up:** [docs/Project_Overview.md](docs/Project_Overview.md)

> **Deployment note:** The Streamlit frontend is deployed on Streamlit Cloud, while the FastAPI backend currently runs locally. Full analysis, history and PDF export require the backend to be running. The deployed frontend cannot directly access a backend running on your personal computer through `localhost`.

---

## Architecture

| Component | Technology | Deployment |
|---|---|---|
| Frontend | Streamlit | Streamlit Cloud / Local |
| Backend API | FastAPI | Local machine (port 8080) |
| Authentication | Supabase Auth | Cloud |
| Database | Supabase | Cloud |
| LLM processing | Groq API | Cloud API |
| Resume processing | spaCy, Sentence Transformers | Local backend |
| PDF generation | WeasyPrint | Local backend |

The application follows a frontend/backend architecture:

- **Streamlit** handles the user interface, authentication flow and API requests.
- **FastAPI** handles resume processing, ATS scoring, LLM-powered analysis, database operations and PDF generation.
- **Supabase** handles authentication and persistent analysis history.
- **Groq** provides LLM capabilities for resume analysis.

The frontend communicates with the backend through HTTP requests, forwarding the Supabase access token for authenticated operations.

---

## Current deployment arrangement

There are two ways to run the application:

### Option 1: Run everything locally (recommended for development)

- Streamlit frontend: http://localhost:8501
- FastAPI backend: http://localhost:8080
- Supabase and Groq remain cloud services.

All application features are available when both services are running.

### Option 2: Use the deployed Streamlit frontend

- Frontend: https://atsscorer-vraj.streamlit.app
- Backend: Not publicly deployed.

The deployed frontend can use Supabase authentication, but it cannot communicate with a backend running on your personal computer through `localhost`.

To enable full functionality from the deployed frontend, the local backend would need to be temporarily exposed through a secure tunnel or deployed to a publicly accessible server.

For the current setup, local frontend and backend execution is used for full demonstrations.

---

## Prerequisites

- Python 3.12 or newer (the backend uses f-string syntax that older versions reject).
- A Supabase project for authentication and analysis history.
- A Groq API key ([console.groq.com](https://console.groq.com)).
- System libraries required by file parsing and PDF generation.

### System dependencies

**macOS (Homebrew)**

```bash
brew install libmagic glib pango cairo gdk-pixbuf libffi
```

WeasyPrint requires native libraries such as GLib, Pango and Cairo in addition to its Python package.

When running the backend on macOS, make sure the dynamic library paths are available to the Python process:

```bash
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:/opt/homebrew/opt/glib/lib:/opt/homebrew/opt/pango/lib:/opt/homebrew/opt/cairo/lib"
```

Run this in the same terminal session used to start Uvicorn.

**Ubuntu / Debian**

```bash
sudo apt install -y libmagic1 libcairo2 libpango-1.0-0 libpangoft2-1.0-0 libffi-dev
```

**Fedora**

```bash
sudo dnf install -y file-libs cairo pango gdk-pixbuf2 libffi
```

**Windows:** WSL is recommended for a consistent development environment with WeasyPrint.

---

## Running locally

All commands are run from the project root (`ATS_SCORER/`).

### 1. Clone the repository and create a virtual environment

```bash
git clone https://github.com/vrajshah2706/ATS_SCORER.git
cd ATS_SCORER

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_md
```

### 3. Configure environment variables

**Backend:** Create `backend/.env`:

```env
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_KEY=<service_role key>
SUPABASE_ANON_KEY=<anon public key>
SUPABASE_JWT_SECRET=<JWT secret>
GROQ_API_KEY=<your groq key>
```

The JWT secret is only required for HS256 token verification. Projects using asymmetric signing keys can use Supabase JWKS verification.

**Frontend:** Create a `.env` file in the project root:

```env
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_ANON_KEY=<anon public key>
```

Alternatively, configure frontend credentials through `.streamlit/secrets.toml`:

```toml
[backend]
url = "http://localhost:8080"

[supabase]
SUPABASE_URL = "https://<your-project>.supabase.co"
SUPABASE_ANON_KEY = "<anon public key>"
```

Both environment files should be git-ignored. **Never commit secret keys.**

### 4. Set up the Supabase database

In the Supabase SQL editor, create the table used to store analysis history:

```sql
create table public.analyses (
  id               bigint generated by default as identity primary key,
  user_id          uuid not null,
  filename         text not null,
  ats_score        numeric,
  keyword_match    numeric,
  missing_keywords jsonb default '[]'::jsonb,
  analysis_result  jsonb not null,
  created_at       timestamptz default now()
);
```

Ensure Row Level Security policies are configured appropriately for your application.

Also enable **Email** sign-in under **Authentication → Providers**.

If email confirmation is enabled, new users must verify their email before signing in.

### 5. Provide the Sentence Transformer model

The backend loads the fine-tuned model from:

```text
backend/core/models/fine_tuned_model/
```

The repository contains the fine-tuned model files (stored through Git LFS).

Alternatively:

1. Download the ZIP generated at the end of `JupyterNotebook/BERT_FINETUNE.ipynb` (`my_finetuned_model.zip`) from Colab.
2. Extract it.
3. Copy the files inside the extracted folder into `backend/core/models/fine_tuned_model/`.
4. Confirm `model.safetensors` is alongside `config.json`.

If the fine-tuned weights are unavailable, use the base model by adding this to `backend/.env`:

```env
SENTENCE_TRANSFORMER_MODEL=all-mpnet-base-v2
```

The model downloads automatically on first start.

### 6. Start the backend

Activate your virtual environment:

```bash
source venv/bin/activate
```

**macOS users:** Set the native library paths before starting the backend:

```bash
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:/opt/homebrew/opt/glib/lib:/opt/homebrew/opt/pango/lib:/opt/homebrew/opt/cairo/lib"
```

Start FastAPI:

```bash
uvicorn backend.main:app --reload --port 8080
```

The first startup can take some time because spaCy and Sentence Transformer models are loaded into memory.

When you see `Application startup complete`, the backend is ready.

Useful endpoints:

- Health check: http://localhost:8080/api/v1/health
- Interactive API documentation: http://localhost:8080/docs

Keep this terminal running while using the application.

### 7. Start the frontend

Open a second terminal:

```bash
cd ~/Desktop/ATS_SCORER
source venv/bin/activate
streamlit run frontend/streamlit_app.py
```

Open: http://localhost:8501

The frontend connects to the local backend using:

```toml
[backend]
url = "http://localhost:8080"
```

### 8. Use the application

1. Create an account or sign in.
2. Open **ATS Scorer**.
3. Upload a PDF or DOCX resume (maximum 5 MB).
4. Select **General ATS Score** or **Job Description Comparison**.
5. Optionally provide a job description.
6. Click **Analyze Resume**.
7. Review the ATS score, feedback and skill validation.
8. Download the generated PDF report.
9. Revisit previous results through **History**.

---

## Frontend and backend configuration

The backend URL is configurable through Streamlit secrets.

For local execution:

```toml
[backend]
url = "http://localhost:8080"
```

For a future publicly hosted backend:

```toml
[backend]
url = "https://<your-backend-url>"
```

> **Important:** Do not configure the deployed Streamlit frontend with `http://localhost:8080` expecting it to reach your personal computer. On Streamlit Cloud, `localhost` refers to the cloud application environment, not your computer.

A publicly accessible backend or secure tunnel is required for communication between the deployed frontend and your local backend.

---

## Troubleshooting

| Problem | Likely cause / solution |
|---|---|
| `Could not reach the backend` | Ensure FastAPI is running on port 8080. |
| Hosted frontend cannot analyse resumes | The hosted frontend cannot reach your local backend without a tunnel or public deployment. |
| `failed to find libmagic` | Install `libmagic` through Homebrew or your operating system package manager. |
| `cannot load library libgobject-2.0-0` | Install GLib, Pango and Cairo. On macOS, export `DYLD_FALLBACK_LIBRARY_PATH` before starting Uvicorn. |
| PDF report generation fails | Check WeasyPrint installation and native system dependencies. |
| spaCy model missing | Run `python -m spacy download en_core_web_md`. |
| Sentence Transformer model missing | Check the model files in `backend/core/models/fine_tuned_model/`. |
| Groq model not found | Check the configured Groq model identifier and current API availability. |
| `401` authentication errors | Sign in again or check Supabase token verification configuration. |
| `Auth not configured on the server` | Check `SUPABASE_URL` and JWT configuration in `backend/.env`. |

---

## Project structure

```text
ATS_SCORER/
├── backend/
│   ├── api/
│   ├── core/
│   ├── services/
│   ├── database/
│   ├── models/
│   ├── templates/
│   └── utils/
├── frontend/
│   ├── views/
│   ├── components/
│   └── services/
├── JupyterNotebook/
├── docs/
├── requirements.txt
└── README.md
```

For architecture diagrams, scoring methodology, model development and design decisions, see [docs/Project_Overview.md](docs/Project_Overview.md).

---

## Future improvements

- Deploy the FastAPI backend to a cloud hosting provider.
- Enable secure communication between the hosted frontend and backend.
- Improve deployment automation and environment configuration.
- Expand resume evaluation and interview preparation capabilities.