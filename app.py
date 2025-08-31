from flask import Flask, render_template, request, jsonify
import os
from dotenv import load_dotenv
from models import Database
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or 'dev-key-for-study-buddy'

# Initialize database
db = Database()

# Initialize database when app starts
print("🚀 Starting AI Study Buddy application...")
db.initialize_database()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate_questions', methods=['POST'])
def generate_questions():
    try:
        data = request.get_json()
        notes = data.get('notes', '')
        num_questions = min(int(data.get('num_questions', 3)), 5)  # Max 5 for demo
        
        # Sample questions for demo - will be replaced with Hugging Face API in Phase 4
        sample_questions = [
            {
                "question": "What is machine learning a subset of?",
                "options": ["Data science", "Artificial intelligence", "Computer programming", "Deep learning"],
                "correctAnswer": 1
            },
            {
                "question": "What does machine learning use to learn for themselves?",
                "options": ["Algorithms", "Data", "Human teachers", "Trial and error"],
                "correctAnswer": 1
            },
            {
                "question": "What does the process of learning begin with?",
                "options": ["Testing", "Programming", "Observations or data", "Algorithm design"],
                "correctAnswer": 2
            },
            {
                "question": "What is the primary aim of machine learning?",
                "options": [
                    "To replace human programmers",
                    "To allow computers to learn automatically without human intervention",
                    "To create sentient AI", 
                    "To process data faster than humans"
                ],
                "correctAnswer": 1
            },
            {
                "question": "What does machine learning look for in data?",
                "options": ["Errors", "Patterns", "Storage efficiency", "Security vulnerabilities"],
                "correctAnswer": 1
            }
        ]
        
        return jsonify({
            "status": "success", 
            "questions": sample_questions[:num_questions]
        })
        
    except Exception as e:
        print(f"❌ Error in generate_questions: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

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
        
        # Create study session
        session_id = db.create_study_session(title, notes)
        
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
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/get_sessions', methods=['GET'])
def get_sessions():
    """Get all study sessions"""
    try:
        sessions = db.get_study_sessions()
        return jsonify({"status": "success", "sessions": sessions})
    except Exception as e:
        print(f"❌ Error in get_sessions: {e}")
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

if __name__ == '__main__':
    app.run(debug=True)