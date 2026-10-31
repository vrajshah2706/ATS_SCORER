"""
- Supabase auth layer for the frontend
- Sits between the UI and Supabase 
- Handles: Supabase Confid, Sign in, Sign up, Sign out and 
converting backend errors into user-readable message
"""
import os
import logging
from pathlib import Path
from typing import Any, Dict
import streamlit as st
from supabase import Client, create_client

logger = logging.getLogger('ats_resume_scorer')

#Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / '.env')
except ImportError:
    pass

# Read configuration from environment or Streamlit secrets
def _secret(key: str, section: str = 'supabase') -> str:
    """Read from env first, then fall back to st.secrets[section][key]."""
    val = os.getenv(key, '')
    if val:
        return val
    try:
        return st.secrets[section][key]
    except (KeyError, FileNotFoundError, AttributeError):
        return ''


SUPABASE_URL = _secret('SUPABASE_URL')
SUPABASE_ANON_KEY = _secret('SUPABASE_ANON_KEY')



def _missing_config() -> str | None:
    #Checks if both values are present
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return 'Supabase is not configured — set SUPABASE_URL and SUPABASE_ANON_KEY in .env or .streamlit/secrets.toml'
    return None

#Fresh client per operation
def get_client() -> Client | None:
    if _missing_config():
        return None
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# Format successful authentication response
def _session_dict(session, user) -> Dict[str, Any]:
    return {
        'access_token':  session.access_token,
        'refresh_token': session.refresh_token,
        'user_id':       user.id,
        'email':         user.email,
    }

# EMAIL/PASSWORD SIGN IN
def sign_in_with_password(email: str, password: str) -> Dict[str, Any]:
    err = _missing_config()
    #Validates config
    if err:
        return {'error': err}
    try:
        #Calls supabase
        resp = get_client().auth.sign_in_with_password(
            {'email': email, 'password': password}
        )
        #Checks if sesssion and user exist
        if not resp.session or not resp.user:
            return {'error': 'Invalid credentials'}
        #Dict of auth info
        return _session_dict(resp.session, resp.user)
    
    except Exception as exc:
        logger.warning(f'sign_in_with_password failed: {exc}')
        return {'error': _humanize(exc)}

# EMAIL/PASSWORD SIGN UP
def sign_up_with_password(email: str, password: str) -> Dict[str, Any]:
    err = _missing_config()
    #Validates config 
    if err:
        return {'error': err}
    try:
        #Calls supabase
        resp = get_client().auth.sign_up({'email': email, 'password': password})
        # 1. session/user exist -> immediate successful signup
        if resp.session and resp.user:
            return _session_dict(resp.session, resp.user)
        # 2. user exists but email confirmation is needed 
        if resp.user:
            return {'pending_confirmation': True, 'email': email}
        
        return {'error': 'Sign-up failed'}
    except Exception as exc:
        logger.warning(f'sign_up failed: {exc}')
        return {'error': _humanize(exc)}

#SIGN OUT
def sign_out(access_token: str, refresh_token: str) -> None:
    if _missing_config():
        return

    try:
        #this way supabase knows which user session to log out
        
        #Recreates a client
        client = get_client()

        #Sets the current session using the provided tokens
        client.auth.set_session(
            access_token,
            refresh_token
        )

        #calls client.auth.sign_out()
        client.auth.sign_out()

        
    except Exception as exc:
        logger.warning(f"Sign out failed: {exc}")

# Convert Supabase errors into readable messages
def _humanize(exc: Exception) -> str:
    msg = str(exc)
    # supabase errors arrive as "<status>: {json blob}" — surface the human bit
    if 'invalid_grant' in msg.lower() or 'invalid login' in msg.lower():
        return 'Wrong email or password'
    if 'user already registered' in msg.lower() or 'already been registered' in msg.lower():
        return 'An account with this email already exists — try signing in'
    if 'password should be at least' in msg.lower():
        return 'Password too short (Supabase default is 6 characters)'
    return msg