import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
from mysql.connector import Error
from config import Config
import json
import pymysql

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
            pool_name="learnlab_pool",
            pool_size=10,  # Adjust based on expected load (5-10 is typical for small apps)
            pool_reset_session=True,
            **self.config
        )
        self.connection = None
    
    def connect(self):
        """Get a connection from the pool"""
        try:
            self.connection = self.pool.get_connection()
            print("✅ Successfully retrieved connection from pool")
            return self.connection
        except Error as e:
            print(f"❌ Error retrieving connection from pool: {e}")
            return None
    
    def disconnect(self):
        """Return connection to pool"""
        if self.connection and self.connection.is_connected():
            self.connection.close()  # Returns connection to pool
            print("✅ Connection returned to pool")
    
    def initialize_database(self):
        """Create necessary tables if they don't exist"""
        print("🔄 Initializing database tables...")
        connection = self.connect()
        if connection is None:
            print("❌ Cannot initialize database: No connection")
            return False
        
        try:
            cursor = connection.cursor()
            
            # Create users table (if not exists)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB
            """)
            print("✅ Users table verified")
            
            # Create study_sessions table with user_id foreign key
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS study_sessions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    notes TEXT,
                    user_id INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    INDEX idx_user_id (user_id),
                    INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB
            """)
            print("✅ Study_sessions table verified")
            
            # Create studycards table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS studycards (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    session_id INT,
                    question TEXT NOT NULL,
                    options JSON NOT NULL,
                    correct_answer INT NOT NULL,
                    user_answer INT,
                    is_correct BOOLEAN,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES study_sessions(id) ON DELETE CASCADE,
                    INDEX idx_session_id (session_id)
                ) ENGINE=InnoDB
            """)
            print("✅ Studycards table verified")
            
            # Create default anonymous user if not exists
            cursor.execute("""
                INSERT IGNORE INTO users (email) 
                VALUES ('anonymous@example.com')
            """)
            print("✅ Default anonymous user verified")
            
            connection.commit()
            print("✅ Database initialization completed successfully")
            return True
            
        except Error as e:
            print(f"❌ Error initializing database: {e}")
            return False
        finally:
            if connection and connection.is_connected():
                cursor.close()
                self.disconnect()

    def create_study_session(self, title, notes, user_id=None):
        """Create a new study session - use provided user_id or current user"""
        print(f"🔄 Creating study session: {title}")
        connection = self.connect()
        if connection is None:
            return None
        
        try:
            cursor = connection.cursor()
            
            # If no user_id provided, try to get from Flask context
            if user_id is None:
                try:
                    from flask import g
                    if hasattr(g, 'user_id') and g.user_id:
                        user_id = g.user_id
                        print(f"✅ Using current user ID: {user_id}")
                except:
                    pass
            
            # If still no user_id, use anonymous user
            if user_id is None:
                cursor.execute("SELECT id FROM users WHERE email = 'anonymous@example.com'")
                anonymous_user = cursor.fetchone()
                user_id = anonymous_user[0] if anonymous_user else None
                print(f"✅ Using anonymous user ID: {user_id}")
            
            cursor.execute(
                "INSERT INTO study_sessions (title, notes, user_id) VALUES (%s, %s, %s)",
                (title, notes, user_id)
            )
            connection.commit()
            session_id = cursor.lastrowid
            print(f"✅ Study session created with ID: {session_id} for user: {user_id}")
            return session_id
        except Error as e:
            print(f"❌ Error creating study session: {e}")
            return None
        finally:
            cursor.close()
            self.disconnect()
    
    def save_flashcards(self, session_id, studycards):
        """Save studycards for a study session"""
        print(f"🔄 Saving {len(studycards)} studycards for session {session_id}")
        connection = self.connect()
        if connection is None:
            return False
        
        try:
            cursor = connection.cursor()
            
            for i, card in enumerate(studycards):
                user_answer = card.get('userAnswer')
                is_correct = (user_answer == card['correctAnswer']) if user_answer is not None else None
                
                cursor.execute(
                    """INSERT INTO studycards 
                    (session_id, question, options, correct_answer, user_answer, is_correct) 
                    VALUES (%s, %s, %s, %s, %s, %s)""",
                    (
                        session_id,
                        card['question'],
                        json.dumps(card['options']),
                        card['correctAnswer'],
                        user_answer,
                        is_correct
                    )
                )
                print(f"✅ Saved flashcard {i+1}: User answered {user_answer}, Correct: {is_correct}")
            
            connection.commit()
            print("✅ All studycards saved successfully")
            return True
            
        except Error as e:
            print(f"❌ Error saving studycards: {e}")
            return False
        finally:
            cursor.close()
            self.disconnect()
    
    def get_sessions(self, user_id=None):
        print(f"🔍 DEBUG: get_sessions called with user_id: {user_id}")
        
        connection = self.connect()
        if connection is None:
            print("❌ DEBUG: Database connection failed")
            return {"status": "error", "message": "Database connection failed"}
        
        cursor = None
        try:
            cursor = connection.cursor(dictionary=True)
            
            # Build the query with proper parameter handling
            query = """
                SELECT 
                    s.id,
                    s.title,
                    s.created_at,
                    DATE_FORMAT(s.created_at, '%Y-%m-%dT%H:%i:%s') AS created_at_formatted,
                    COUNT(c.id) AS total_questions,
                    SUM(CASE WHEN c.is_correct = 1 THEN 1 ELSE 0 END) as correct_answers,
                    CASE 
                        WHEN COUNT(c.id) > 0 
                        THEN ROUND(SUM(CASE WHEN c.is_correct = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(c.id), 2) 
                        ELSE 0 
                    END AS score_percentage
                FROM study_sessions s
                LEFT JOIN studycards c ON s.id = c.session_id
            """
            
            # Add WHERE clause if user_id is provided
            if user_id is not None:
                query += " WHERE s.user_id = %(user_id)s"
                params = {'user_id': user_id}
            else:
                params = {}
            
            # Add GROUP BY and ORDER BY
            query += " GROUP BY s.id, s.title, s.created_at ORDER BY s.created_at DESC"
            
            print(f"🔍 DEBUG: Executing query: {query}")
            print(f"🔍 DEBUG: With params: {params}")
            
            # Use named parameters instead of positional
            cursor.execute(query, params)
            
            sessions = cursor.fetchall()
            print(f"🔍 DEBUG: Found {len(sessions)} sessions")

            # Convert to appropriate types
            formatted_sessions = []
            for s in sessions:
                formatted_sessions.append({
                    "id": s["id"],
                    "title": s["title"],
                    "created_at": s["created_at"],
                    "created_at_formatted": s["created_at_formatted"],
                    "total_questions": int(s["total_questions"]) if s.get("total_questions") is not None else 0,
                    "correct_answers": int(s["correct_answers"]) if s.get("correct_answers") is not None else 0,
                    "score_percentage": float(s["score_percentage"]) if s.get("score_percentage") is not None else 0.0
                })

            print(f"🔍 DEBUG: Returning {len(formatted_sessions)} formatted sessions")
            return {"status": "success", "sessions": formatted_sessions}
                
        except Error as e:
            print(f"❌ Error retrieving sessions: {e}")
            import traceback
            traceback.print_exc()
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
            
            # Try to get existing user
            cursor.execute("SELECT id, email FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
            
            if user:
                print(f"✅ Found existing user: {user['email']} (ID: {user['id']})")
                return user
            
            # Create new user
            cursor.execute("INSERT INTO users (email) VALUES (%s)", (email,))
            connection.commit()
            user_id = cursor.lastrowid
            
            # Get the created user
            cursor.execute("SELECT id, email FROM users WHERE id = %s", (user_id,))
            new_user = cursor.fetchone()
            
            print(f"✅ Created new user: {email} (ID: {user_id})")
            return new_user
            
        except Error as e:
            print(f"❌ Error getting/creating user: {e}")
            return None
        finally:
            if connection and connection.is_connected():
                cursor.close()
                self.disconnect()

    def get_sessions_for_chart(self, user_id=None, limit=10):
        """Get sessions specifically formatted for chart data"""
        print(f"🔍 DEBUG: get_sessions_for_chart called with user_id: {user_id}, limit: {limit}")
        
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
                    DATE_FORMAT(s.created_at, '%Y-%m-%d %H:%i:%s') AS created_at_formatted,
                    COUNT(c.id) AS total_questions,
                    SUM(CASE WHEN c.is_correct = 1 THEN 1 ELSE 0 END) AS correct_answers,
                    CASE 
                        WHEN COUNT(c.id) > 0 
                        THEN ROUND(SUM(CASE WHEN c.is_correct = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(c.id), 2) 
                        ELSE 0 
                    END AS score_percentage
                FROM study_sessions s
                LEFT JOIN studycards c ON s.id = c.session_id
            """
            
            # Build WHERE clause and parameters
            params = {}
            where_clauses = []
            
            if user_id is not None:
                where_clauses.append("s.user_id = %(user_id)s")
                params['user_id'] = user_id
            else:
                # If no user specified, include anonymous sessions
                cursor.execute("SELECT id FROM users WHERE email = 'anonymous@example.com'")
                anonymous_user = cursor.fetchone()
                if anonymous_user:
                    where_clauses.append("s.user_id = %(anonymous_user_id)s")
                    params['anonymous_user_id'] = anonymous_user['id']
            
            # Add WHERE clause if needed
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
            
            query += " GROUP BY s.id, s.title, s.created_at ORDER BY s.created_at DESC LIMIT %(limit)s"
            params['limit'] = limit
            
            print(f"🔍 DEBUG: Executing chart query: {query}")
            print(f"🔍 DEBUG: With params: {params}")
            
            cursor.execute(query, params)
            sessions = cursor.fetchall()

            # Convert to appropriate types and format for chart
            formatted_sessions = []
            for s in sessions:
                formatted_sessions.append({
                    "id": s["id"],
                    "title": s["title"],
                    "created_at": s["created_at"],
                    "created_at_formatted": s["created_at_formatted"],
                    "total_questions": int(s["total_questions"]) if s.get("total_questions") is not None else 0,
                    "correct_answers": int(s["correct_answers"]) if s.get("correct_answers") is not None else 0,
                    "score_percentage": float(s["score_percentage"]) if s.get("score_percentage") is not None else 0.0
                })
            
            return formatted_sessions
            
        except Error as e:
            print(f"❌ Error retrieving sessions for chart: {e}")
            import traceback
            traceback.print_exc()
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
                "SELECT * FROM studycards WHERE session_id = %s ORDER BY id",
                (session_id,)
            )
            
            studycards = cursor.fetchall()
            for card in studycards:
                card['options'] = json.loads(card['options'])
            
            return studycards
            
        except Error as e:
            print(f"❌ Error retrieving studycards: {e}")
            return []
        finally:
            cursor.close()
            self.disconnect()

    def delete_session(self, session_id):
        """Delete a study session and its associated cards"""
        print(f"🔄 Deleting session {session_id}")
        connection = self.connect()
        if connection is None:
            return False
        
        try:
            cursor = connection.cursor()
            
            # First delete associated studycards (due to foreign key constraint)
            cursor.execute("DELETE FROM studycards WHERE session_id = %s", (session_id,))
            print(f"✅ Deleted studycards for session {session_id}")
            
            # Then delete the session
            cursor.execute("DELETE FROM study_sessions WHERE id = %s", (session_id,))
            connection.commit()
            
            print(f"✅ Successfully deleted session {session_id}")
            return True
            
        except Error as e:
            print(f"❌ Error deleting session {session_id}: {e}")
            connection.rollback()
            return False
        finally:
            if connection and connection.is_connected():
                cursor.close()
                self.disconnect()
