from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
from dotenv import load_dotenv
from models import Database
from datetime import datetime, timezone, timedelta
import requests
import json
import re
from cachetools import TTLCache


load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(24).hex()

# Initialize database
db = Database()
db.initialize_database()

session_cache = TTLCache(maxsize=100, ttl=60)  # 60-second TTL, max 100 users

def get_user_sessions(user_id):
    """Get sessions from cache or database"""
    cache_key = f"sessions_{user_id}"
    
    # Check cache first
    try:
        if cache_key in session_cache:
            return session_cache[cache_key]
    except Exception:
        pass
    
    # Fetch from database
    result = db.get_sessions(user_id)
    sessions = result.get('sessions', []) if isinstance(result, dict) and result.get('status') == 'success' else []
    
    # Store in cache
    try:
        session_cache[cache_key] = sessions
    except Exception:
        pass
    
    return sessions

def invalidate_user_cache(user_id):
    """Invalidate cache for a user's sessions"""
    cache_key = f"sessions_{user_id}"
    try:
        if cache_key in session_cache:
            del session_cache[cache_key]
    except Exception:
        pass

def balance_correct_answers(questions):
    """
    Ensure correct answers are distributed across different positions (A, B, C, D)
    to prevent patterns like all answers being 'A'
    """
    if not questions or len(questions) <= 1:
        return questions
    
    positions = [0, 1, 2, 3]  # A, B, C, D
    position_count = {0: 0, 1: 0, 2: 0, 3: 0}
    
    # Count current distribution
    for q in questions:
        pos = q['correctAnswer']
        if pos in position_count:
            position_count[pos] += 1
    
    # Check if we need to rebalance (if any position has more than its fair share)
    max_allowed = (len(questions) // 4) + 1
    needs_rebalancing = any(count > max_allowed for count in position_count.values())
    
    if not needs_rebalancing:
        return questions  # Distribution is already good
    
    print(f"📊 Rebalancing answer positions. Current distribution: A={position_count[0]}, B={position_count[1]}, C={position_count[2]}, D={position_count[3]}")
    
    # STRATEGY 1: Try to balance by processing questions in random order
    import random
    question_indices = list(range(len(questions)))
    random.shuffle(question_indices)  # Process questions in random order
    
    # STRATEGY 2: Create a target distribution
    target_distribution = {}
    total_questions = len(questions)
    base_count = total_questions // 4
    remainder = total_questions % 4
    
    # Distribute questions evenly among positions
    for i, pos in enumerate(positions):
        target_distribution[pos] = base_count + (1 if i < remainder else 0)
    
    print(f"🎯 Target distribution: A={target_distribution[0]}, B={target_distribution[1]}, C={target_distribution[2]}, D={target_distribution[3]}")
    
    # STRATEGY 3: Smart rebalancing with multiple passes
    rebalanced_count = 0
    
    # First pass: Fix severely overused positions
    for i in question_indices:
        q = questions[i]
        current_pos = q['correctAnswer']
        
        # Only rebalance if this position is over target
        if position_count[current_pos] > target_distribution[current_pos]:
            # Find positions that are under target, prioritizing least used
            underused_positions = [
                pos for pos in positions 
                if position_count[pos] < target_distribution[pos]
            ]
            
            if underused_positions:
                # Choose the most underused position
                new_pos = min(underused_positions, key=lambda p: position_count[p])
                
                # Swap the correct answer with the new position
                correct_text = q['options'][current_pos]
                other_text = q['options'][new_pos]
                
                q['options'][current_pos] = other_text
                q['options'][new_pos] = correct_text
                q['correctAnswer'] = new_pos
                
                position_count[current_pos] -= 1
                position_count[new_pos] += 1
                rebalanced_count += 1
                print(f"🔄 Swapped Q{i+1} from position {current_pos} to {new_pos}")
                
                # Early exit if we've achieved good distribution
                if all(position_count[pos] <= target_distribution[pos] for pos in positions):
                    break
    
    # STRATEGY 4: If still unbalanced, do a second pass with different logic
    if any(position_count[pos] > target_distribution[pos] for pos in positions):
        print("🔁 Second pass needed for fine-tuning")
        
        # Process in reverse order this time
        for i in reversed(question_indices):
            q = questions[i]
            current_pos = q['correctAnswer']
            
            # If this position is still overused
            if position_count[current_pos] > target_distribution[current_pos]:
                # Find any position that's underused
                for new_pos in positions:
                    if (new_pos != current_pos and 
                        position_count[new_pos] < target_distribution[new_pos]):
                        
                        # Swap
                        correct_text = q['options'][current_pos]
                        other_text = q['options'][new_pos]
                        
                        q['options'][current_pos] = other_text
                        q['options'][new_pos] = correct_text
                        q['correctAnswer'] = new_pos
                        
                        position_count[current_pos] -= 1
                        position_count[new_pos] += 1
                        rebalanced_count += 1
                        print(f"🔄 Second pass: Swapped Q{i+1} from {current_pos} to {new_pos}")
                        break
    
    print(f"✅ Balanced {rebalanced_count} questions. Final distribution: A={position_count[0]}, B={position_count[1]}, C={position_count[2]}, D={position_count[3]}")
    return questions

def generate_questions_with_gemini(notes, num_questions=6, question_type="mcq", difficulty="normal"):
    """
    Generate quiz questions using Google Gemini API with performance optimizations.
    """
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("❌ No Gemini API key found")
        return None, "no_api_key"
    
    # ✅ OPTIMIZED: Use a single reliable model
    PRIMARY_MODEL = 'gemini-2.0-flash-001'  # Fastest model
    FALLBACK_MODEL = 'gemini-pro'  # Single fallback
    
    # ✅ OPTIMIZED: Streamline prompt construction
    prompt = build_optimized_prompt(notes, num_questions, question_type, difficulty)
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        
        models_to_try = [PRIMARY_MODEL, FALLBACK_MODEL]
        
        for model_name in models_to_try:
            print(f"🔄 Attempting with model: {model_name}")
            
            try:
                # ✅ CORRECTED: Remove timeout from generation_config
                model = genai.GenerativeModel(
                    model_name=model_name,
                    generation_config={
                        "temperature": 0.8,
                        "max_output_tokens": 1500,  # Reduced for faster response
                    }
                )
                
                # ✅ CORRECTED: Timeout only in request_options
                response = model.generate_content(
                    prompt, 
                    request_options={"timeout": 10}  # 10-second timeout
                )
                
                if response and response.text:
                    print("✅ API call successful!")
                    return process_api_response(response.text, num_questions, question_type, difficulty)
                    
            except Exception as e:
                print(f"❌ Model {model_name} failed: {str(e)}")
                if "quota" in str(e).lower():
                    return None, "quota_exceeded"
                continue
                
        return None, "api_error"
                
    except ImportError:
        return None, "module_missing"
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return None, "api_error"

def build_optimized_prompt(notes, num_questions, question_type, difficulty):
    """Build optimized prompt with reduced length"""
    # Truncate notes more aggressively
    truncated_notes = notes[:1500]  # Reduced from 2000
    
    type_instructions = {
        "mcq": f"Generate {num_questions} multiple-choice questions with 4 options each.",
        "tf": f"Generate {num_questions} True/False questions with 2 options each."
    }
    
    difficulty_instructions = {
        "normal": "Focus on factual recall and basic understanding.",
        "difficult": "Test deeper understanding and application."
    }
    
    return f"""
Create a quiz based on these notes. Keep questions concise.

{type_instructions.get(question_type, type_instructions['mcq'])}
{difficulty_instructions.get(difficulty, difficulty_instructions['normal'])}

NOTES: {truncated_notes}

Return as JSON: {{"questions": [{{"question": "...", "options": ["A","B"], "correctAnswer": 0}}]}}
"""

def process_api_response(response_text, num_questions, question_type, difficulty):
    """Process API response efficiently"""
    try:
        # Find JSON more efficiently
        json_str = extract_json_from_text(response_text)
        if not json_str:
            return None, "invalid_response"
            
        questions_data = json.loads(json_str)
        raw_questions = questions_data.get('questions', [])[:num_questions]  # Limit early
        
        if not raw_questions:
            return None, "no_questions"
            
        # Apply post-processing
        processed_questions = []
        for q in raw_questions:
            q.update({
                "question_type": question_type,
                "difficulty": difficulty
            })
            processed_questions.append(q)
        
        # Balance answers only if needed and we have enough questions
        if question_type == "mcq" and len(processed_questions) >= 2:
            processed_questions = balance_correct_answers(processed_questions)
            
        return processed_questions, "success"
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON parsing failed: {e}")
        return None, "parse_error"

def extract_json_from_text(text):
    """Efficiently extract JSON from response text"""
    start = text.find('{')
    end = text.rfind('}') + 1
    return text[start:end] if start >= 0 and end > start else None

def get_sample_questions(num_questions, question_type="mcq", difficulty="normal"):
    """Return sample questions as fallback with support for question types and difficulty levels"""
    
    # Base sample questions with all required fields
    sample_pool = {
        "mcq": {
            "normal": [
                {
                    "question": "What is the capital of France?",
                    "options": ["Paris", "London", "Berlin", "Madrid"],
                    "correctAnswer": 0,
                    "question_type": "mcq",
                    "difficulty": "normal"
                },
                {
                    "question": "Which planet is known as the Red Planet?",
                    "options": ["Venus", "Mars", "Jupiter", "Saturn"],
                    "correctAnswer": 1,
                    "question_type": "mcq",
                    "difficulty": "normal"
                },
                {
                    "question": "What is 2 x 0.2?",
                    "options": ["2.2", "0.4", "4.4", "0.04"],
                    "correctAnswer": 1,
                    "question_type": "mcq",
                    "difficulty": "normal"
                },
                {
                    "question": "How do you say 'hello' in Japanese?",
                    "options": ["Ni hao", "Anyeong", "Konnichiwa", "Ola"],
                    "correctAnswer": 2,
                    "question_type": "mcq",
                    "difficulty": "normal"
                }
            ],
            "difficult": [
                {
                    "question": "In machine learning, what technique involves training multiple models and combining their predictions?",
                    "options": ["Gradient descent", "Ensemble learning", "Backpropagation", "Regularization"],
                    "correctAnswer": 1,
                    "question_type": "mcq",
                    "difficulty": "difficult"
                },
                {
                    "question": "Which architectural pattern is most commonly associated with microservices?",
                    "options": ["Monolithic", "Hexagonal", "Layered", "Event-driven"],
                    "correctAnswer": 3,
                    "question_type": "mcq",
                    "difficulty": "difficult"
                },
                {
                    "question": "What is the time complexity of a well-balanced binary search tree?",
                    "options": ["O(1)", "O(n)", "O(log n)", "O(n log n)"],
                    "correctAnswer": 2,
                    "question_type": "mcq",
                    "difficulty": "difficult"
                },
                {
                    "question": "Which psychological concept describes the tendency to favor information that confirms existing beliefs?",
                    "options": ["Cognitive dissonance", "Confirmation bias", "Hindsight bias", "Anchoring effect"],
                    "correctAnswer": 1,
                    "question_type": "mcq",
                    "difficulty": "difficult"
                }
            ]
        },
        "tf": {
            "normal": [
                {
                    "question": "Paris is the capital of France.",
                    "options": ["True", "False"],
                    "correctAnswer": 0,
                    "question_type": "tf",
                    "difficulty": "normal"
                },
                {
                    "question": "Water boils at 100 degrees Celsius at sea level.",
                    "options": ["True", "False"],
                    "correctAnswer": 0,
                    "question_type": "tf",
                    "difficulty": "normal"
                },
                {
                    "question": "The Great Wall of China is visible from space with the naked eye.",
                    "options": ["True", "False"],
                    "correctAnswer": 1,
                    "question_type": "tf",
                    "difficulty": "normal"
                },
                {
                    "question": "Sharks are mammals.",
                    "options": ["True", "False"],
                    "correctAnswer": 1,
                    "question_type": "tf",
                    "difficulty": "normal"
                }
            ],
            "difficult": [
                {
                    "question": "In quantum computing, qubits can exist in superposition of both 0 and 1 states simultaneously.",
                    "options": ["True", "False"],
                    "correctAnswer": 0,
                    "question_type": "tf",
                    "difficulty": "difficult"
                },
                {
                    "question": "The CAP theorem states that a distributed system can simultaneously achieve consistency, availability, and partition tolerance.",
                    "options": ["True", "False"],
                    "correctAnswer": 1,
                    "question_type": "tf",
                    "difficulty": "difficult"
                },
                {
                    "question": "Photosynthesis occurs in the mitochondria of plant cells.",
                    "options": ["True", "False"],
                    "correctAnswer": 1,
                    "question_type": "tf",
                    "difficulty": "difficult"
                },
                {
                    "question": "The Riemann Hypothesis has been proven to be true.",
                    "options": ["True", "False"],
                    "correctAnswer": 1,
                    "question_type": "tf",
                    "difficulty": "difficult"
                }
            ]
        }
    }
    
    # Get the appropriate sample pool based on question type and difficulty
    selected_pool = sample_pool.get(question_type, {}).get(difficulty, [])
    
    # If no specific pool found, fall back to MCQ normal
    if not selected_pool:
        selected_pool = sample_pool["mcq"]["normal"]
        # Update the questions to match the requested type and difficulty
        for question in selected_pool:
            question["question_type"] = question_type
            question["difficulty"] = difficulty
    
    # Return the requested number of questions, cycling through the pool if needed
    if len(selected_pool) >= num_questions:
        return selected_pool[:num_questions]
    else:
        # Repeat the pool to meet the required number
        repeated_pool = (selected_pool * ((num_questions // len(selected_pool)) + 1))[:num_questions]
        return repeated_pool

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

@app.route('/auth/logout')
def auth_logout():
    """Log out user - UPDATED WITH CACHE INVALIDATION"""
    user_id = session.get('user_id')
    user_email = session.get('user_email', 'Unknown')
    
    if user_id:
        invalidate_user_cache(user_id)  # Invalidate cache on logout
        
    session.pop('user_id', None)
    session.pop('user_email', None)
    print(f"✅ User logged out: {user_email}")
    return jsonify({"status": "success", "message": "Logged out successfully"})

@app.before_request
def require_auth():
    # Allow these routes without authentication
    if request.path in ['/auth/login', '/auth/status', '/', '/static/', '/contact']:
        return None
    
    # Allow static files
    if request.path.startswith('/static/'):
        return None
    
    # Check if user is authenticated
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Authentication required"}), 401
    
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate_questions', methods=['POST'])
def generate_questions():
    try:
        user_id = session.get('user_id')
        if user_id:
            allowance = db.check_session_allowance(user_id)
            if not allowance['allowed']:
                return jsonify({
                    "status": "error", 
                    "code": "SESSION_LIMIT_EXCEEDED",
                    "message": f"Free tier limited to {allowance['limit']} sessions per day",
                    "reset_in": allowance['reset_in'],
                    "remaining": allowance['remaining'],
                    "limit": allowance['limit']
                }), 429  # Too Many Requests

        data = request.get_json()        
        notes = data.get('notes', '')
        num_questions = min(int(data.get('num_questions', 6)), 12)
        question_type = data.get('question_type', 'mcq')
        difficulty = data.get('difficulty', 'normal')
        
        if not notes or not notes.strip():
            return jsonify({"status": "error", "message": "Please provide study notes"}), 400
        
        # Try AI generation with Gemini
        ai_questions, api_status = generate_questions_with_gemini(notes, num_questions, question_type, difficulty)
                
        # Sample questions as fallback
        sample_questions = get_sample_questions(num_questions, question_type, difficulty)
                
        if ai_questions:
            response_data = {
                "status": "success", 
                "questions": ai_questions[:num_questions],
                "source": "ai",
                "message": "Questions generated by AI"
            }
            return jsonify(response_data)
        else:
            response_data = {
                "status": "success", 
                "questions": sample_questions[:num_questions],
                "source": "sample",
                "message": "Using sample questions"
            }
            return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error in generate_questions: {str(e)}")
        import traceback
        traceback.print_exc()  # This will show the full error stack
        return jsonify({"status": "error", "message": f"Internal server error: {str(e)}"}), 500

@app.route('/save_flashcards', methods=['POST'])
def save_flashcards():
    try:
        data = request.get_json()
        flashcards = data.get('flashcards', [])
        notes = data.get('notes', '')
        session_start_time = data.get('session_start_time')
        session_end_time = data.get('session_end_time') 
        session_duration = data.get('session_duration', 0)
        
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
        
        # Get user_id from session
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"status": "error", "message": "Authentication required"}), 401
        
        if user_id:
            allowance = db.check_session_allowance(user_id)
            if not allowance['allowed']:
                return jsonify({
                    "status": "error", 
                    "code": "SESSION_LIMIT_EXCEEDED",
                    "message": f"Free tier limited to {allowance['limit']} sessions per day",
                    "reset_in": allowance['reset_in'],
                    "remaining": allowance['remaining'],
                    "limit": allowance['limit']
                }), 429
        
        # Convert ISO timestamps to MySQL format
        def convert_to_mysql_datetime(iso_string):
            """Convert ISO 8601 string to MySQL datetime format in UTC+3"""
            if not iso_string:
                return None
            try:
                # Parse ISO string
                dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
                
                # Convert to UTC+3 (East Africa Time)
                dt_utc3 = dt.astimezone(timezone(timedelta(hours=3)))
                
                # Format for MySQL
                return dt_utc3.strftime('%Y-%m-%d %H:%M:%S')
            except (ValueError, AttributeError):
                print(f"❌ Failed to parse timestamp: {iso_string}")
                return None
        
        mysql_start_time = convert_to_mysql_datetime(session_start_time)
        mysql_end_time = convert_to_mysql_datetime(session_end_time)
        
        if not mysql_start_time or not mysql_end_time:
            return jsonify({"status": "error", "message": "Invalid timestamp format"}), 400
        
        # Create study session with converted timestamps
        title = f"Study Session {datetime.now().strftime('%Y-%m-%d at %H:%M')}"
        query = """
            INSERT INTO study_sessions 
            (title, notes, user_id, created_at, updated_at, session_duration) 
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        # Convert milliseconds to seconds for storage
        duration_seconds = session_duration / 1000
        session_id = db.execute_query(query, (
            title, 
            notes, 
            user_id,
            mysql_start_time,  # created_at = start time
            mysql_end_time,    # updated_at = end time  
            duration_seconds   # session_duration in seconds
        ))
        
        if not session_id:
            return jsonify({"status": "error", "message": "Failed to create study session"}), 500
        
        # Save flashcards
        success = db.save_flashcards(session_id, flashcards)
        if not success:
            # If flashcards fail, delete the orphaned session
            db.execute_query("DELETE FROM study_sessions WHERE id = %s", (session_id,))
            return jsonify({"status": "error", "message": "Failed to save flashcards"}), 500
        
        # UPDATE SESSION USAGE COUNT
        if user_id:
            # Increment appropriate session counter based on tier
            connection = db.get_connection()
            if connection:
                try:
                    cursor = connection.cursor(dictionary=True)
                    
                    # Check user tier to determine which counter to increment
                    cursor.execute("SELECT subscription_tier, period_reset_date, sessions_used_this_period FROM users WHERE id = %s", (user_id,))
                    user_tier_data = cursor.fetchone()
                    
                    print(f"🔍 DEBUG: User {user_id}, Tier: {user_tier_data['subscription_tier']}")
                    print(f"🔍 DEBUG: Pre-update - Reset Date: {user_tier_data['period_reset_date']}, Period Sessions: {user_tier_data['sessions_used_this_period']}")
                    if user_tier_data:
                        # Initialize period reset date for paid users on first session
                        if (user_tier_data['subscription_tier'] != 'free' and 
                            user_tier_data['period_reset_date'] is None and 
                            user_tier_data['sessions_used_this_period'] == 0):
                            print(f"🔍 DEBUG: Initializing reset period for {user_tier_data['subscription_tier']} tier")

                            # TIER-SPECIFIC reset periods
                            if user_tier_data['subscription_tier'] == 'silver':
                                days_to_add = 30
                            elif user_tier_data['subscription_tier'] == 'gold':
                                days_to_add = 365
                            else:
                                days_to_add = 30  # Default fallback
                            
                            next_reset_date = datetime.now() + timedelta(days=days_to_add)
                            cursor.execute("""
                                UPDATE users SET period_reset_date = %s 
                                WHERE id = %s
                            """, (next_reset_date, user_id))
                            
                            print(f"DEBUG: User {user_id}, Tier: {user_tier_data['subscription_tier']}, Setting reset date: {next_reset_date}, Days to add: {days_to_add}")
                        
                    # Increment the appropriate counter
                    if user_tier_data['subscription_tier'] == 'free':
                        # Free tier: increment daily counter
                        cursor.execute("""
                            UPDATE users 
                            SET sessions_used_today = sessions_used_today + 1,
                                total_sessions_used = total_sessions_used + 1
                            WHERE id = %s
                        """, (user_id,))
                    else:
                        # Paid tiers: increment period counter
                        cursor.execute("""
                            UPDATE users 
                            SET sessions_used_this_period = sessions_used_this_period + 1,
                                total_sessions_used = total_sessions_used + 1
                            WHERE id = %s
                        """, (user_id,))
                    
                    connection.commit()
                        
                except Exception as e:
                    print(f"Error updating session count: {e}")
                finally:
                    if cursor:
                        cursor.close()
                    connection.close()
        
        invalidate_user_cache(user_id)
        return jsonify({
            "status": "success", 
            "message": "Flashcards saved successfully",
            "session_id": session_id
        })
        
    except Exception as e:
        print(f"❌ Exception in save_flashcards: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/get_sessions', methods=['GET'])
def get_sessions_route():
    """Get all study sessions for current user"""
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({"status": "error", "message": "Authentication required"}), 401
            
        result = db.get_sessions(user_id)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Error in /get_sessions: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": "Internal server error"}), 500

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
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"status": "error", "message": "Authentication required"}), 401
            
        if db.delete_session(session_id):
            invalidate_user_cache(user_id)  # Invalidate cache after deletion
            return jsonify({"status": "success", "message": "Session deleted successfully"})
        else:
            return jsonify({"status": "error", "message": "Failed to delete session"}), 500
            
    except Exception as e:
        print(f"Error deleting session {session_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/list_sessions')
def list_sessions():
    """Get sessions list for current user with proper duration calculation"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"status": "error", "message": "Authentication required"}), 401
        
        # Use the new helper method
        sessions = db.get_user_sessions_with_analytics(user_id)

        
        # Process sessions
        processed_sessions = []
        for session_data in sessions:
            total = session_data['total_questions'] or 0
            correct = session_data['correct_answers'] or 0
            score = round((correct / total) * 100, 1) if total > 0 else 0
            
            # Convert datetime objects to ISO format strings
            processed_session = {
                'id': session_data['id'],
                'title': session_data['title'],
                'notes': session_data['notes'],
                'total_questions': total,
                'score_percentage': score,
                'session_duration': session_data['session_duration'] or 0
            }
            
            # Add timestamp fields only if they exist
            if session_data['created_at']:
                processed_session['created_at'] = session_data['created_at'].isoformat()
            if session_data['updated_at']:
                processed_session['updated_at'] = session_data['updated_at'].isoformat()
            if session_data['session_start_time']:
                processed_session['session_start_time'] = session_data['session_start_time'].isoformat()
            if session_data['session_end_time']:
                processed_session['session_end_time'] = session_data['session_end_time'].isoformat()
            
            processed_sessions.append(processed_session)
        
        return jsonify({
            "status": "success", 
            "sessions": processed_sessions
        })
        
    except Exception as e:
        print(f"Error in list_sessions: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500

@app.route('/progress-data')
def progress_data():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401
            
        sessions = get_user_sessions(user_id)  # Use cached version
        
        # Prepare data for chart.js
        data = {
            "labels": [s['created_at_formatted'] for s in sessions[:10]],
            "scores": [float(s['score_percentage']) for s in sessions[:10]],
            "questions": [s['total_questions'] for s in sessions[:10]]
        }
        return jsonify(data)
        
    except Exception as e:
        return jsonify({"error": str(e)})

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

@app.route('/user/tier-info')
def user_tier_info():
    """Get user's subscription tier information - FIXED VERSION"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({
                "status": "success",
                "tier_info": {
                    "tier": "free",
                    "remaining_sessions": 3,
                    "session_limit": 3,
                    "sessions_used_today": 0,
                    "reset_in": "24h 0m",
                    "billing_period": "daily"
                }
            })

        allowance = db.check_session_allowance(user_id)
        
        # Get additional tier info
        connection = db.get_connection()
        if connection:
            try:
                cursor = connection.cursor(dictionary=True)
                cursor.execute("""
                    SELECT subscription_tier, total_sessions_used 
                    FROM users WHERE id = %s
                """, (user_id,))
                user_data = cursor.fetchone()
            finally:
                cursor.close()
                connection.close()
        else:
            user_data = {"subscription_tier": "free", "total_sessions_used": 0}

        return jsonify({
            "status": "success",
            "tier_info": {
                "tier": user_data.get('subscription_tier', 'free'),
                "remaining_sessions": allowance['remaining'],
                "session_limit": allowance['limit'],
                "sessions_used_today": allowance.get('sessions_used_today', 0),
                "reset_in": allowance['reset_in'],
                "billing_period": allowance['period'],
                "total_sessions_used": user_data.get('total_sessions_used', 0)
            }
        })

    except Exception as e:
        print(f"Error getting tier info: {e}")
        return jsonify({
            "status": "error", 
            "message": "Internal server error"
        }), 500 

@app.route('/upgrade')
def upgrade_page():
    """Render the upgrade/pricing page"""
    return render_template('upgrade.html')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html')

@app.route('/sessions')
def sessions():
    return render_template('sessions.html')

@app.route('/analytics/type-difficulty')
def analytics_type_difficulty():
    """Get aggregated type and difficulty analytics"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"status": "error", "message": "Authentication required"}), 401
        
        analytics_data = db.get_analytics_type_difficulty(user_id)
        
        if analytics_data is None:
            return jsonify({"status": "error", "message": "Failed to fetch analytics data"}), 500
        
        return jsonify({
            "status": "success",
            "data": analytics_data
        })
        
    except Exception as e:
        print(f"Error in analytics_type_difficulty: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500

@app.route('/analytics/type-difficulty-filtered', methods=['POST'])
def analytics_type_difficulty_filtered():
    """Get analytics for specific session IDs"""
    connection = None
    cursor = None
    try:       
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"status": "error", "message": "Authentication required"}), 401
        
        data = request.get_json()
        session_ids = data.get('session_ids', [])
        
        if not session_ids:
            return jsonify({
                "status": "success",
                "data": {
                    "question_types": [],
                    "difficulties": []
                }
            })
        
        # Convert to tuple for SQL IN clause
        session_ids_tuple = tuple(session_ids)
        if len(session_ids) == 1:
            session_ids_tuple = f"({session_ids[0]})"
        
        connection = db.get_connection()
        if not connection:
            return jsonify({"status": "error", "message": "Database connection failed"}), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Query for question type analytics
        type_query = f"""
            SELECT 
                sc.question_type,
                COUNT(*) as total_questions,
                SUM(CASE WHEN sc.is_correct = 1 THEN 1 ELSE 0 END) as correct_answers
            FROM studycards sc
            WHERE sc.session_id IN {session_ids_tuple}
            GROUP BY sc.question_type
        """
        cursor.execute(type_query)
        type_data = cursor.fetchall()
        
        # Query for difficulty analytics
        difficulty_query = f"""
            SELECT 
                sc.difficulty,
                COUNT(*) as total_questions,
                SUM(CASE WHEN sc.is_correct = 1 THEN 1 ELSE 0 END) as correct_answers
            FROM studycards sc
            WHERE sc.session_id IN {session_ids_tuple}
            GROUP BY sc.difficulty
        """
        
        cursor.execute(difficulty_query)
        difficulty_data = cursor.fetchall()
        
        result = {
            'question_types': type_data,
            'difficulties': difficulty_data
        }
        
        return jsonify({
            "status": "success",
            "data": result
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": "Internal server error"}), 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@app.route('/debug/pool-status')
def debug_pool_status():
    try:
        # Use the public API, not private attributes
        try:
            # Try to get a connection to test if pool works
            test_conn = db.get_connection()
            if test_conn:
                test_conn.close()
                status = "Pool working"
            else:
                status = "Pool failed"
        except Exception as e:
            status = f"Pool error: {e}"
        
        return jsonify({
            "status": "success",
            "pool_status": status,
            "pool_size": db.pool.pool_size if hasattr(db, 'pool') else 'No pool'
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Route to render contact page
@app.route('/contact', methods=['GET'])
def contact_page():
    return render_template('contact.html')

# AJAX endpoint to receive contact form and send email
@app.route('/contact', methods=['POST'])
def send_contact():
    try:
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        message_body = data.get('message', '').strip()

        # Basic server-side validation
        if not name or not email or not message_body:
            return jsonify({'status': 'error', 'message': 'Please provide name, email and message.'}), 400

        # Build email
        recipients = [os.environ.get('CONTACT_DESTINATION_EMAIL', app.config.get('MAIL_USERNAME'))]
        subject = f"Contact form message from {name}"
        body = f"Name: {name}\nEmail: {email}\n\nMessage:\n{message_body}"

        msg = Message(subject=subject, sender=app.config.get('MAIL_DEFAULT_SENDER'), recipients=recipients, body=body, reply_to=email)
        mail.send(msg)

        return jsonify({'status': 'success', 'message': 'Message sent successfully!'}), 200

    except Exception as e:
        print("Error sending contact email:", e)
        return jsonify({'status': 'error', 'message': 'Failed to send message. Please try again later.'}), 500

@app.route('/user/session-allowance')
def user_session_allowance():
    """Get user's current session allowance"""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({
                "status": "success",
                "allowance": {
                    "allowed": True,
                    "remaining": 999,
                    "limit": 999,
                    "reset_in": "unlimited",
                    "period": "daily"
                }
            })
        
        allowance = db.check_session_allowance(user_id)
        return jsonify({
            "status": "success",
            "allowance": allowance
        })
        
    except Exception as e:
        print(f"Error getting session allowance: {e}")
        return jsonify({
            "status": "error",
            "message": "Failed to get session allowance"
        }), 500

@app.route('/user/session-count')
def user_session_count():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"status": "success", "session_count": 0})
    
    # Simple query - just get sessions_used_today
    result = db.fetch_one("SELECT sessions_used_today FROM users WHERE id = %s", (user_id,))
    return jsonify({"status": "success", "session_count": result['sessions_used_today'] if result else 0})

if __name__ == '__main__':
    # Use environment variable for host/port in production
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5000))
    app.run(host=host, port=port, debug=os.environ.get('DEBUG', 'False').lower() == 'true')