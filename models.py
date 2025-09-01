import mysql.connector
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
        self.connection = None
    
    def connect(self):
        """Establish database connection"""
        try:
            self.connection = mysql.connector.connect(**self.config)
            print("✅ Successfully connected to MySQL database")
            return self.connection
        except Error as e:
            print(f"❌ Error connecting to MySQL: {e}")
            return None
    
    def disconnect(self):
        """Close database connection"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
    
    def initialize_database(self):
        """Create necessary tables if they don't exist"""
        print("🔄 Initializing database tables...")
        connection = self.connect()
        if connection is None:
            print("❌ Cannot initialize database: No connection")
            return False
        
        try:
            cursor = connection.cursor()
            
            # Create study_sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS study_sessions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)
            print("✅ Created study_sessions table")
            
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
                    FOREIGN KEY (session_id) REFERENCES study_sessions(id) ON DELETE CASCADE
                )
            """)
            print("✅ Created studycards table")
            
            connection.commit()
            print("✅ Database tables initialized successfully")
            return True
            
        except Error as e:
            print(f"❌ Error creating tables: {e}")
            return False
        finally:
            cursor.close()
            self.disconnect()
    
    def create_study_session(self, title, notes):
        """Create a new study session and return its ID"""
        print(f"🔄 Creating study session: {title}")
        connection = self.connect()
        if connection is None:
            return None
        
        try:
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO study_sessions (title, notes) VALUES (%s, %s)",
                (title, notes)
            )
            connection.commit()
            session_id = cursor.lastrowid
            print(f"✅ Study session created with ID: {session_id}")
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
    
    def get_sessions(self):
        connection = self.connect()
        if connection is None:
            return []
        try:
            with connection.cursor(dictionary=True) as cursor:  # Use the connection variable
                cursor.execute("""
                    SELECT 
                        s.id,
                        s.title,
                        s.created_at,  # Keep original for sorting
                        DATE_FORMAT(s.created_at, '%Y-%m-%dT%H:%i:%s') AS created_at_formatted,
                        COUNT(c.id) AS total_questions,
                        SUM(CASE WHEN c.is_correct = 1 THEN 1 ELSE 0 END) AS correct_answers,
                        CASE 
                            WHEN COUNT(c.id) > 0 
                            THEN ROUND(SUM(CASE WHEN c.is_correct = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(c.id), 2) 
                            ELSE 0 
                        END AS score_percentage
                    FROM study_sessions s
                    LEFT JOIN studycards c ON s.id = c.session_id
                    GROUP BY s.id, s.title, s.created_at
                    ORDER BY s.created_at DESC  
                """)
                sessions = cursor.fetchall()

                # Convert Decimals to appropriate types
                for s in sessions:
                    if s.get("score_percentage") is not None:
                        s["score_percentage"] = float(s["score_percentage"])
                    else:
                        s["score_percentage"] = 0.0
                        
                    if s.get("correct_answers") is not None:
                        s["correct_answers"] = int(s["correct_answers"])
                    else:
                        s["correct_answers"] = 0

                print("DEBUG sessions:", sessions)
                return {"status": "success", "sessions": sessions}
        except Error as e:
            print(f"❌ Error retrieving sessions: {e}")
            return {"status": "error", "message": str(e)}
        finally:
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
