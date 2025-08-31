import os

class Config:
    # Basic configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-for-study-buddy'
    
    # Database configuration
    DB_HOST = os.environ.get('DB_HOST') or 'localhost'
    DB_USER = os.environ.get('DB_USER') or 'study_buddy_user'
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or 'your_password_here'
    DB_NAME = os.environ.get('DB_NAME') or 'study_buddy_db'
    
    # Hugging Face API configuration
    HF_API_KEY = os.environ.get('HF_API_KEY') or ''
    HF_API_URL = os.environ.get('HF_API_URL') or 'https://api-inference.huggingface.co/models'