import mysql.connector
from mysql.connector import Error
from config import Config
import json

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
    
    def get_study_sessions(self):
        """Retrieve all study sessions"""
        connection = self.connect()
        if connection is None:
            return []
        
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM study_sessions ORDER BY created_at DESC")
            return cursor.fetchall()
        except Error as e:
            print(f"❌ Error retrieving study sessions: {e}")
            return []
        finally:
            cursor.close()
            self.disconnect()
    
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