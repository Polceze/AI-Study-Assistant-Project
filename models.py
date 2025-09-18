from mysql.connector import Error
from mysql.connector.pooling import MySQLConnectionPool
from mysql.connector import Error
from config import Config
import json
from datetime import datetime, timedelta

class Database:
    def __init__(self):
        self.config = {
            'host': Config.DB_HOST,
            'database': Config.DB_NAME,
            'user': Config.DB_USER,
            'password': Config.DB_PASSWORD
        }
        # Initialize connection pool
        self.pool = MySQLConnectionPool(
            pool_name="reviseAI_pool",
            pool_size=10,
            pool_reset_session=True,
            **self.config
        )
    
    def get_connection(self):
        """Get a connection from the pool"""
        return self.pool.get_connection()

    def execute_query(self, query, params=None):
        """Run INSERT/UPDATE/DELETE queries"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(query, params or ())
            conn.commit()
            return cursor.lastrowid  # useful for inserts
        except Error as e:
            print(f"Database error: {e}")
            conn.rollback()
            return None
        finally:
            cursor.close()
            conn.close()

    def fetch_all(self, query, params=None):
        """Run SELECT queries that return multiple rows"""
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)  # rows as dicts
        try:
            cursor.execute(query, params or ())
            return cursor.fetchall()
        except Error as e:
            print(f"Database error: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def connect(self):
        """Get a connection from the pool"""
        try:
            self.connection = self.pool.get_connection()
            return self.connection
        except Error as e:
            print(f"Error retrieving connection from pool: {e}")
            return None
    
    def disconnect(self):
        """Return connection to pool"""
        if self.connection and self.connection.is_connected():
            self.connection.close()

    def initialize_database(self):
        """Create necessary tables if they don't exist"""
        connection = self.connect()
        if connection is None:
            return False
        
        try:
            cursor = connection.cursor()

            # --- Users table ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    subscription_tier VARCHAR(20) DEFAULT 'free',
                    subscription_start_date TIMESTAMP NULL,
                    sessions_used_today INT DEFAULT 0,
                    last_session_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_sessions_used INT DEFAULT 0,
                    payment_status VARCHAR(20) DEFAULT 'inactive'
                ) ENGINE=InnoDB
            """)

            # --- Subscription Plans ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subscription_plans (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(50) UNIQUE NOT NULL,
                    price FLOAT NOT NULL,
                    session_limit INT NOT NULL,
                    billing_period VARCHAR(20) NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB
            """)

            # --- Payments ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    plan_id INT NOT NULL,
                    amount FLOAT NOT NULL,
                    payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(20) DEFAULT 'pending',
                    transaction_id VARCHAR(100),
                    invoice_id VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (plan_id) REFERENCES subscription_plans(id) ON DELETE CASCADE,
                    INDEX idx_user_id (user_id),
                    INDEX idx_plan_id (plan_id),
                    INDEX idx_status (status)
                ) ENGINE=InnoDB
            """)

            # --- Study Sessions ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS study_sessions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    notes TEXT,
                    user_id INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    session_duration float,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    INDEX idx_user_id (user_id),
                    INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB
            """)

            # --- Studycards ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS studycards (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    session_id INT,
                    question TEXT NOT NULL,
                    options JSON NOT NULL,
                    correct_answer INT NOT NULL,
                    user_answer INT,
                    is_correct BOOLEAN,
                    question_type VARCHAR(20) DEFAULT 'mcq',
                    difficulty VARCHAR(20) DEFAULT 'normal',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    saved_at TIMESTAMP NULL DEFAULT NULL,
                    FOREIGN KEY (session_id) REFERENCES study_sessions(id) ON DELETE CASCADE,
                    INDEX idx_session_id (session_id),
                    INDEX idx_question_type (question_type),
                    INDEX idx_difficulty (difficulty)
                ) ENGINE=InnoDB
            """)

            # --- Default Anonymous User ---
            cursor.execute("""
                INSERT IGNORE INTO users (email) 
                VALUES ('anonymous@example.com')
            """)

            connection.commit()
            return True

        except Error as e:
            print(f"Error initializing database: {e}")
            return False
        finally:
            if connection and connection.is_connected():
                cursor.close()
                self.disconnect()

    def create_study_session(self, title, notes, user_id):
        """Create a study session and return session ID"""
        try:
            query = "INSERT INTO study_sessions (title, notes, user_id) VALUES (%s, %s, %s)"
            session_id = self.execute_query(query, (title, notes, user_id))
            return session_id
        except Error as e:
            print(f"Error creating study session: {e}")
            return None

    def save_flashcards(self, session_id, flashcards):
        """Save flashcards for a session with type and difficulty"""
        try:
            # Delete any existing flashcards for this session
            delete_query = "DELETE FROM studycards WHERE session_id = %s"
            self.execute_query(delete_query, (session_id,))
            
            # Insert new flashcards with type and difficulty
            for card in flashcards:
                user_answer = card.get('userAnswer')
                correct_answer = card.get('correctAnswer', 0)
                is_correct = user_answer is not None and user_answer == correct_answer
                
                # Get question type and difficulty from the card
                question_type = card.get('questionType', card.get('question_type', 'mcq'))
                difficulty = card.get('difficulty', 'normal')
                
                query = """
                    INSERT INTO studycards 
                    (session_id, question, options, correct_answer, user_answer, 
                    is_correct, question_type, difficulty)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                params = (
                    session_id,
                    card.get('question', ''),
                    json.dumps(card.get('options', [])),
                    correct_answer,
                    user_answer,
                    is_correct,
                    question_type,
                    difficulty
                )
                self.execute_query(query, params)
                
                print(f"💾 Saved card - Type: {question_type}, Difficulty: {difficulty}")
            
            return True
            
        except Error as e:
            print(f"Error saving flashcards: {e}")
            return False

    def get_sessions(self, user_id=None):
        """Get study sessions for a user, including score and question type summary"""
        connection = self.connect()
        if connection is None:
            return {"status": "error", "message": "Database connection failed"}
        
        cursor = None
        try:
            cursor = connection.cursor(dictionary=True)
            
            query = """
                SELECT 
                    s.id,
                    s.title,
                    s.created_at,
                    s.updated_at,
                    s.session_duration,
                    DATE_FORMAT(s.created_at, '%%Y-%%m-%%dT%%H:%%i:%%s') AS created_at_formatted,
                    COUNT(c.id) AS total_questions,
                    SUM(CASE WHEN c.is_correct = 1 THEN 1 ELSE 0 END) as correct_answers,
                    CASE 
                        WHEN COUNT(c.id) > 0 
                        THEN ROUND(SUM(CASE WHEN c.is_correct = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(c.id), 2) 
                        ELSE 0 
                    END AS score_percentage,
                    GROUP_CONCAT(DISTINCT c.question_type) AS question_types
                FROM study_sessions s
                LEFT JOIN studycards c ON s.id = c.session_id
            """
            
            params = {}
            if user_id is not None:
                query += " WHERE s.user_id = %(user_id)s"
                params['user_id'] = user_id
            
            query += " GROUP BY s.id, s.title, s.created_at ORDER BY s.created_at DESC"
            
            cursor.execute(query, params)
            sessions = cursor.fetchall()

            formatted_sessions = []
            for s in sessions:
                types = []
                if s.get("question_types"):
                    types = list(set(s["question_types"].split(",")))  # deduplicate
                
                formatted_sessions.append({
                    "id": s["id"],
                    "title": s["title"],
                    "created_at": s["created_at"],
                    "created_at_formatted": s["created_at_formatted"],
                    "total_questions": int(s["total_questions"]) if s.get("total_questions") is not None else 0,
                    "correct_answers": int(s["correct_answers"]) if s.get("correct_answers") is not None else 0,
                    "score_percentage": float(s["score_percentage"]) if s.get("score_percentage") is not None else 0.0,
                    "question_types": types,
                    "session_duration": float(s["session_duration"]) if s.get("session_duration") is not None else None,
                    "updated_at": s["updated_at"]
                })

            return {"status": "success", "sessions": formatted_sessions}
                
        except Error as e:
            print(f"Error retrieving sessions: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()
    
    def get_or_create_user(self, email):
        """Get user by email, create if not exists"""
        connection = self.connect()
        if connection is None:
            return None
        
        try:
            cursor = connection.cursor(dictionary=True)
            
            cursor.execute("SELECT id, email FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
            
            if user:
                return user
            
            cursor.execute("INSERT INTO users (email) VALUES (%s)", (email,))
            connection.commit()
            user_id = cursor.lastrowid
            
            cursor.execute("SELECT id, email FROM users WHERE id = %s", (user_id,))
            return cursor.fetchone()
            
        except Error as e:
            print(f"Error getting/creating user: {e}")
            return None
        finally:
            if connection and connection.is_connected():
                cursor.close()
                self.disconnect()

    def get_sessions_for_chart(self, user_id=None, limit=10):
        """Get sessions for chart data, including score and question type summary"""
        connection = self.connect()
        if connection is None:
            return []
        
        cursor = None
        try:
            cursor = connection.cursor(dictionary=True)
            
            query = """
                SELECT 
                    s.id,
                    s.title,
                    s.created_at,
                    s.updated_at,
                    s.session_duration,
                    DATE_FORMAT(s.created_at, '%%Y-%%m-%%dT%%H:%%i:%%s') AS created_at_formatted,
                    COUNT(c.id) AS total_questions,
                    SUM(CASE WHEN c.is_correct = 1 THEN 1 ELSE 0 END) as correct_answers,
                    CASE 
                        WHEN COUNT(c.id) > 0 
                        THEN ROUND(SUM(CASE WHEN c.is_correct = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(c.id), 2) 
                        ELSE 0 
                    END AS score_percentage,
                    GROUP_CONCAT(DISTINCT c.question_type) AS question_types
                FROM study_sessions s
                LEFT JOIN studycards c ON s.id = c.session_id
            """
            
            params = {}
            where_clauses = []
            
            if user_id is not None:
                where_clauses.append("s.user_id = %(user_id)s")
                params['user_id'] = user_id
            else:
                cursor.execute("SELECT id FROM users WHERE email = 'anonymous@example.com'")
                anonymous_user = cursor.fetchone()
                if anonymous_user:
                    where_clauses.append("s.user_id = %(anonymous_user_id)s")
                    params['anonymous_user_id'] = anonymous_user['id']
            
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
            
            query += " GROUP BY s.id, s.title, s.created_at ORDER BY s.created_at DESC LIMIT %(limit)s"
            params['limit'] = limit
            
            cursor.execute(query, params)
            sessions = cursor.fetchall()

            formatted_sessions = []
            for s in sessions:
                types = []
                if s.get("question_types"):
                    types = list(set(s["question_types"].split(",")))  # deduplicate
                
                formatted_sessions.append({
                    "id": s["id"],
                    "title": s["title"],
                    "created_at": s["created_at"],
                    "created_at_formatted": s["created_at_formatted"],
                    "total_questions": int(s["total_questions"]) if s.get("total_questions") is not None else 0,
                    "correct_answers": int(s["correct_answers"]) if s.get("correct_answers") is not None else 0,
                    "score_percentage": float(s["score_percentage"]) if s.get("score_percentage") is not None else 0.0,
                    "question_types": types,
                    "session_duration": float(s["session_duration"]) if s.get("session_duration") is not None else None,
                    "updated_at": s["updated_at"]
                })
            
            return formatted_sessions
            
        except Error as e:
            print(f"Error retrieving sessions for chart: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    def get_flashcards_by_session(self, session_id):
        """Retrieve studycards for a specific study session"""
        connection = self.connect()
        if connection is None:
            return []
        
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                """SELECT id, session_id, question, question_type, options, 
                        correct_answer, user_answer, is_correct, created_at, saved_at
                FROM studycards 
                WHERE session_id = %s 
                ORDER BY id""",
                (session_id,)
            )
            
            studycards = cursor.fetchall()
            for card in studycards:
                # Parse JSON options into Python list
                card['options'] = json.loads(card['options'])
            
            return studycards
            
        except Error as e:
            print(f"Error retrieving studycards: {e}")
            return []
        finally:
            cursor.close()
            self.disconnect()

    def delete_session(self, session_id):
        """Delete a study session and its associated cards"""
        connection = self.connect()
        if connection is None:
            return False
        
        try:
            cursor = connection.cursor()
            
            cursor.execute("DELETE FROM studycards WHERE session_id = %s", (session_id,))
            cursor.execute("DELETE FROM study_sessions WHERE id = %s", (session_id,))
            connection.commit()
            
            return True
            
        except Error as e:
            print(f"Error deleting session {session_id}: {e}")
            connection.rollback()
            return False
        finally:
            if connection and connection.is_connected():
                cursor.close()
                self.disconnect()
    
    def get_user_tier_info(self, user_id):
        """Get user's subscription tier and usage information"""
        connection = self.connect()
        if connection is None:
            return None

        try:
            cursor = connection.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT 
                    u.subscription_tier,
                    u.sessions_used_today,
                    u.last_session_reset,
                    u.total_sessions_used,
                    p.session_limit,
                    p.billing_period
                FROM users u
                LEFT JOIN subscription_plans p ON u.subscription_tier = p.name
                WHERE u.id = %s
            """, (user_id,))
            
            result = cursor.fetchone()
            
            if result:
                # Calculate remaining sessions and reset time
                remaining_sessions = max(0, result['session_limit'] - result['sessions_used_today'])
                
                # Calculate time until reset based on billing period
                reset_time = None
                if result['billing_period'] == 'daily':
                    # Next reset is tomorrow at same time as last reset
                    reset_time = result['last_session_reset'] + timedelta(days=1)
                elif result['billing_period'] == 'monthly':
                    # Next reset is next month
                    reset_time = result['last_session_reset'] + timedelta(days=30)
                elif result['billing_period'] == 'yearly':
                    # Next reset is next year
                    reset_time = result['last_session_reset'] + timedelta(days=365)
                
                time_until_reset = reset_time - datetime.now() if reset_time else None
                
                return {
                    'tier': result['subscription_tier'],
                    'sessions_used_today': result['sessions_used_today'],
                    'session_limit': result['session_limit'],
                    'remaining_sessions': remaining_sessions,
                    'last_reset': result['last_session_reset'],
                    'next_reset': reset_time,
                    'time_until_reset': time_until_reset,
                    'billing_period': result['billing_period'],
                    'total_sessions_used': result['total_sessions_used']
                }
            
            return None

        except Error as e:
            print(f"Error getting user tier info: {e}")
            return None
        finally:
            if connection and connection.is_connected():
                cursor.close()
                self.disconnect()

    def get_user_sessions_with_analytics(self, user_id):
        """Get user sessions with analytics data"""
        query = """
            SELECT 
                ss.*,
                COUNT(sc.id) as total_questions,
                SUM(CASE WHEN sc.is_correct = 1 THEN 1 ELSE 0 END) as correct_answers,
                ss.created_at as session_start_time,
                ss.updated_at as session_end_time,
                ss.session_duration as session_duration
            FROM study_sessions ss
            LEFT JOIN studycards sc ON ss.id = sc.session_id
            WHERE ss.user_id = %s
            GROUP BY ss.id
            ORDER BY ss.created_at DESC
        """
        return self.fetch_all(query, (user_id,))

    def get_analytics_type_difficulty(self, user_id):
        """Get aggregated analytics data for question types and difficulties"""
        connection = self.connect()
        if connection is None:
            return None
        
        try:
            cursor = connection.cursor(dictionary=True)
            
            # Query for question type analytics
            type_query = """
                SELECT 
                    sc.question_type,
                    COUNT(*) as total_questions,
                    SUM(CASE WHEN sc.is_correct = 1 THEN 1 ELSE 0 END) as correct_answers
                FROM studycards sc
                JOIN study_sessions ss ON sc.session_id = ss.id
                WHERE ss.user_id = %s
                GROUP BY sc.question_type
            """
            
            # Query for difficulty analytics
            difficulty_query = """
                SELECT 
                    sc.difficulty,
                    COUNT(*) as total_questions,
                    SUM(CASE WHEN sc.is_correct = 1 THEN 1 ELSE 0 END) as correct_answers
                FROM studycards sc
                JOIN study_sessions ss ON sc.session_id = ss.id
                WHERE ss.user_id = %s
                GROUP BY sc.difficulty
            """
            
            cursor.execute(type_query, (user_id,))
            type_data = cursor.fetchall()
            
            cursor.execute(difficulty_query, (user_id,))
            difficulty_data = cursor.fetchall()
            
            # Format the results
            result = {
                'question_types': type_data,
                'difficulties': difficulty_data
            }
            
            return result
            
        except Error as e:
            print(f"Error getting analytics data: {e}")
            return None
        finally:
            if connection and connection.is_connected():
                cursor.close()
                self.disconnect()
                