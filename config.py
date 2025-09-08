import os

class Config:
    # Basic configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-for-study-buddy'
    
    # Database configuration
    DB_HOST = os.environ.get('DB_HOST') or 'localhost'
    DB_USER = os.environ.get('DB_USER') or 'reviseAI_user'
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or 'password123'
    DB_NAME = os.environ.get('DB_NAME') or 'reviseAI_DB'
    
    # Gemini API configuration
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') or ''
    GEMINI_API_URL = os.environ.get('GEMINI_API_URL') or 'https://generativelanguage.googleapis.com/v1beta/models'