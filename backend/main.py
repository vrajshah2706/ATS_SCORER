import logging 
from contextlib import asynccontextmanager 
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import (
    ALLOWED_ORIGINS, 
    APP_DESCRIPTION,
    APP_TITLE,
    APP_VERSION,
    SPACY_MODEL_PRIMARY,
    SPACY_MODEL_SECONDARY,
    SENTENCE_TRANSFORMER_MODEL,
)

from backend.api.routes import router 

#all the logs will be under this logger name 
logger = logging.getLogger('ats_resume_scorer') 

#context manager for the lifespan of the app 
#this is where we  load the models and other resources before the app starts serving requests
@asynccontextmanager
async def lifespan(app:FastAPI):
    logger.info("Staring ATS Reumse Analyzer API ...")

    logger.info(f"Loading spacy NLP model: {SPACY_MODEL_PRIMARY} ")
    import spacy 
    try: 
        app.state.nlp = spacy.load(SPACY_MODEL_PRIMARY) #loading spacy model 
        logger.info(f"Loaded {SPACY_MODEL_PRIMARY}")
    except OSError: 
        logger.warning(f"{SPACY_MODEL_PRIMARY} not found - falling back to {SPACY_MODEL_SECONDARY}")
        app.state.nlp = spacy.load(SPACY_MODEL_SECONDARY) #loading fallback model
        logger.info(f"Loaded {SPACY_MODEL_SECONDARY} (fallback)")

    logger.info(f"Loading SentenceTransformer: {SENTENCE_TRANSFORMER_MODEL}")
    from sentence_transformers import SentenceTransformer 
    app.state.embedder = SentenceTransformer(
        SENTENCE_TRANSFORMER_MODEL
    )
    logger.info(f"Loaded SentenceTransformer: {SENTENCE_TRANSFORMER_MODEL}")

    logger.info("All models loaded. API is ready to serve requests.")

    #everything above this line is executed before the app starts serving requests, 
    yield 
    #everything below this line is executed when the app is shutting down

    logger.info("Shutting down the api!!")

#loading the api with metadata and lifespan context manager
app = FastAPI(
    title=APP_TITLE,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url = '/docs',
    redoc_url = "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[*ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

if __name__ == '__main__':
    import uvicorn 
    uvicorn.run(
        "backend.main:app",
        host = "0.0.0.0",
        port = 8000,
        reload = True, #Auto restart on code changes (dev only)
    )

#to run -> uvicorn backend.main:app --reload




