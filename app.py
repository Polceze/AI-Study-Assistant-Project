from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
from dotenv import load_dotenv
from models import Database
from datetime import datetime, timedelta
import requests
import json
import uuid
import re

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(24).hex()

# Initialize database
db = Database()

# Initialize database when app starts
print("🚀 Starting AI Study Buddy application...")
db.initialize_database()

def generate_questions_with_gemini(notes, num_questions=6):
    """
    Generate quiz questions using Google Gemini API
    """
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("❌ No Gemini API key found")
        return None, "no_api_key"
    
    try:
        # Try multiple endpoint formats - one of these should work
        endpoints = [
            f"https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent?key={api_key}",                        
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={api_key}",
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",            
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.0-pro:generateContent?key={api_key}",
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={api_key}"
        ]
        
        prompt = f"""
        You are an expert educational assistant. Generate {num_questions} diverse multiple-choice study questions based on the following notes. 
        Each question should have exactly 4 plausible answer options (A, B, C, D), with only one correct answer. 
        Questions should test memorization and understanding but should not be too obscure. Return the result in JSON format with the following structure for each question.
        Mark the correct answer with the corresponding letter (0 for A, 1 for B, 2 for C, 3 for D)
        
        STUDY NOTES:
        {notes[:2000]}
        
        {{
            "questions": [
                {{
                    "question": "Question text here",
                    "options": ["Option A", "Option B", "Option C", "Option D"],
                    "correctAnswer": 0
                }}
            ]
        }}
        """
        
        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2000
            }
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Try each endpoint until one works
        for API_URL in endpoints:
            print(f"🔄 Trying endpoint: {API_URL.split('/')[-1].split('?')[0]}")
            
            try:
                response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
                print(f"Response status: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    print("✅ Gemini API call successful with this endpoint!")
                    
                    # Extract the generated text
                    if 'candidates' in result and len(result['candidates']) > 0:
                        generated_text = result['candidates'][0]['content']['parts'][0]['text']
                        print(f"Generated text: {generated_text[:200]}...")
                        
                        # Extract JSON from the response
                        try:
                            json_start = generated_text.find('{')
                            json_end = generated_text.rfind('}') + 1
                            if json_start >= 0 and json_end > json_start:
                                json_str = generated_text[json_start:json_end]
                                questions_data = json.loads(json_str)
                                print(f"✅ Successfully generated {len(questions_data.get('questions', []))} questions")
                                return questions_data.get('questions', []), "success"
                            else:
                                print("❌ No JSON found in response")
                                # Continue to next endpoint instead of failing
                                continue
                                
                        except json.JSONDecodeError as e:
                            print(f"❌ JSON parsing error: {e}")
                            print(f"Raw response: {generated_text[:500]}...")
                            # Continue to next endpoint
                            continue
                    else:
                        print("❌ Unexpected response format:", result)
                        # Continue to next endpoint
                        continue
                        
                elif response.status_code == 404:
                    print(f"❌ Endpoint not found: {response.text[:200]}...")
                    # Try next endpoint
                    continue
                    
                else:
                    print(f"❌ API Error: {response.status_code}")
                    print(f"Error details: {response.text[:200]}...")
                    # Try next endpoint
                    continue
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ Network error with endpoint: {e}")
                # Try next endpoint
                continue
                
        # If we get here, all endpoints failed
        print("❌ All Gemini API endpoints failed")
        return None, "api_error"
            
    except Exception as e:
        print(f"❌ Unexpected error with Gemini API: {e}")
        import traceback
        traceback.print_exc()
        return None, "error"


def get_sample_questions(num_questions):
    """Return sample questions as fallback"""
    sample_questions = [
        {
            "question": "What is the capital of France?",
            "options": ["Paris", "London", "Berlin", "Madrid"],
            "correctAnswer": 0
        },
        {
            "question": "What field is machine learning a subset of?",
            "options": ["Data science", "Computer programming", "Deep learning", "Artificial intelligence"],
            "correctAnswer": 3
        },
        {
            "question": "Which planet is known as the Red Planet?",
            "options": ["Venus", "Mars", "Jupiter", "Saturn"],
            "correctAnswer": 1
        },
        {
            "question": "What is 2 x 0.2?",
            "options": ["2.2", "0.4", "4.4", "0.04"],
            "correctAnswer": 1
        },
        {
            "question": "How do you say 'hello' in Japanese?",
            "options": ["Ni hao", "Anyeong", "Konnichiwa", "Ola"],
            "correctAnswer": 2
        },
        {
            "question": "What device uses sunlight to tell time?",
            "options": ["Quartz", "An hourglass", "A pendulum", "A sundial"],
            "correctAnswer": 3
        }

    ]
    return sample_questions[:num_questions]


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/generate_questions', methods=['POST'])
def generate_questions():
    try:
        data = request.get_json()
        notes = data.get('notes', '')
        num_questions = min(int(data.get('num_questions', 6)), 12) # Limit to max 12 questions, default 6
        
        if not notes or not notes.strip():
            return jsonify({"status": "error", "message": "Please provide study notes"}), 400
        
        # Try AI generation with Gemini
        ai_questions, api_status = generate_questions_with_gemini(notes, num_questions)
        
        # Sample questions as fallback
        sample_questions = get_sample_questions(num_questions)
        
        if ai_questions:
            return jsonify({
                "status": "success", 
                "questions": ai_questions[:num_questions],
                "source": "ai",
                "message": "Questions generated by AI"
            })
        else:
            error_messages = {
                "no_api_key": "AI features disabled - no API key configured",
                "api_error": "AI service error - using sample questions",
                "parse_error": "AI response format issue - using sample questions",
                "error": "AI generation failed - using sample questions"
            }
            
            return jsonify({
                "status": "success", 
                "questions": sample_questions[:num_questions],
                "source": "sample",
                "message": error_messages.get(api_status, "Using sample questions")
            })
        
    except Exception as e:
        print(f"❌ Error in generate_questions: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500


@app.route('/save_flashcards', methods=['POST'])
def save_flashcards():
    try:
        data = request.get_json()
        flashcards = data.get('flashcards', [])
        notes = data.get('notes', '')
        title = f"Study Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        print(f"💾 Received save request with {len(flashcards)} flashcards")
        
        # Validate data
        if not flashcards:
            return jsonify({"status": "error", "message": "No flashcards to save"}), 400
        
        # Check for unanswered questions
        unanswered = [i for i, card in enumerate(flashcards) if card.get('userAnswer') is None]
        if unanswered:
            return jsonify({
                "status": "error", 
                "message": f"Please answer all questions first. Unanswered: {len(unanswered)}",
                "unanswered": unanswered
            }), 400
        
        # Get user_id from session (now properly set by auth)
        user_id = session.get('user_id')
        print(f"💾 Saving for user ID: {user_id}")
        
        if not user_id:
            return jsonify({"status": "error", "message": "Authentication required"}), 401
        
        # Create study session
        session_id = db.create_study_session(title, notes, user_id)
        
        if not session_id:
            return jsonify({"status": "error", "message": "Failed to create study session"}), 500
        
        # Save flashcards
        if db.save_flashcards(session_id, flashcards):
            return jsonify({
                "status": "success", 
                "message": "Flashcards saved successfully",
                "session_id": session_id
            })
        else:
            return jsonify({"status": "error", "message": "Failed to save flashcards"}), 500
        
    except Exception as e:
        print(f"❌ Exception in save_flashcards: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/get_sessions', methods=['GET'])
def get_sessions_route():
    """Get all study sessions for current user"""
    try:
        user_id = session.get('user_id')
        print(f"🔍 DEBUG: User ID from session: {user_id}")
        
        if not user_id:
            print("❌ DEBUG: No user_id in session - authentication required")
            return jsonify({"status": "error", "message": "Authentication required"}), 401
            
        result = db.get_sessions(user_id)
                
        return jsonify(result)
    except Exception as e:
        print(f"❌ Error in get_sessions: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/get_flashcards/<int:session_id>', methods=['GET'])
def get_flashcards(session_id):
    """Get flashcards for a specific session"""
    try:
        flashcards = db.get_flashcards_by_session(session_id)
        return jsonify({"status": "success", "flashcards": flashcards})
    except Exception as e:
        print(f"❌ Error in get_flashcards: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/delete_session/<int:session_id>', methods=['DELETE'])
def delete_session(session_id):
    try:
        db = Database()
        success = db.delete_session(session_id)
        
        if success:
            return jsonify({"status": "success", "message": "Session deleted successfully"})
        else:
            return jsonify({"status": "error", "message": "Failed to delete session"}), 500
            
    except Exception as e:
        print(f"Error deleting session {session_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/list_sessions', methods=['GET'])
def list_sessions():
    """Get sessions list for current user"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"status": "error", "message": "Authentication required"}), 401
            
        result = db.get_sessions(user_id)
                
        if result.get('status') == 'success':
            return jsonify({"status": "success", "sessions": result.get('sessions', [])})
        else:
            return jsonify({"status": "error", "message": result.get('message', 'Unknown error')})
    except Exception as e:
        print(f"❌ Error in list_sessions: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    

@app.route('/progress-data')
def progress_data():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401
            
        limit = int(request.args.get('limit', 10))
        result = db.get_sessions(user_id)
        
        if result.get('status') == 'success':
            sessions = result.get('sessions', [])
            # Prepare data for chart.js
            data = {
                "labels": [s['created_at_formatted'] for s in sessions[:limit]],
                "scores": [float(s['score_percentage']) for s in sessions[:limit]],
                "questions": [s['total_questions'] for s in sessions[:limit]]
            }
            return jsonify(data)
        else:
            return jsonify({"error": result.get('message', 'Unknown error')})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/auth/login', methods=['POST'])
def auth_login():
    """Handle email-only login"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        
        # Basic email validation
        if not email or not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            return jsonify({"status": "error", "message": "Please enter a valid email address"}), 400
        
        # Get or create user in database
        user = db.get_or_create_user(email)
        if not user:
            return jsonify({"status": "error", "message": "Failed to create user account"}), 500
        
        # Set user session
        session['user_id'] = user['id']
        session['user_email'] = user['email']
        
        print(f"✅ User logged in: {user['email']} (ID: {user['id']})")
        
        return jsonify({
            "status": "success", 
            "message": "Login successful",
            "user": {
                "id": user['id'],
                "email": user['email']
            }
        })
        
    except Exception as e:
        print(f"❌ Login error: {e}")
        return jsonify({"status": "error", "message": "Login failed. Please try again."}), 500


@app.route('/auth/logout')
def auth_logout():
    """Log out user"""
    user_email = session.get('user_email', 'Unknown')
    session.pop('user_id', None)
    session.pop('user_email', None)
    print(f"✅ User logged out: {user_email}")
    return jsonify({"status": "success", "message": "Logged out successfully"})


@app.route('/auth/status')
def auth_status():
    """Check authentication status"""
    user_id = session.get('user_id')
    user_email = session.get('user_email')
    
    return jsonify({
        "status": "success",
        "authenticated": user_id is not None,
        "user": {
            "id": user_id,
            "email": user_email
        } if user_id else None
    })

@app.route('/chart-data')
def chart_data():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401
            
        limit = int(request.args.get('limit', 5))
        sessions = db.get_sessions_for_chart(user_id, limit)
        
        data = {
            "labels": [s['created_at_formatted'] for s in sessions],
            "scores": [float(s['score_percentage']) for s in sessions],
            "questions": [s['total_questions'] for s in sessions]
        }
        return jsonify(data)
        
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    # Use environment variable for host/port in production
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5000))
    app.run(host=host, port=port, debug=os.environ.get('DEBUG', 'False').lower() == 'true')