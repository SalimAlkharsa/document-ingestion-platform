import sqlite3
import os
import logging
from datetime import datetime
from pathlib import Path

# Add the parent directory to sys.path to import globals
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from globals import DB_DIR, DOCUMENTS_DB_PATH

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DocumentDBHandler:
    """Handler for document processing database operations"""
    
    def __init__(self):
        """Initialize the database connection and create tables if they don't exist"""
        # Ensure the database directory exists
        os.makedirs(DB_DIR, exist_ok=True)
        
        self.conn = None
        self.connect()
        self.create_tables()
    
    def connect(self):
        """Connect to the SQLite database"""
        try:
            self.conn = sqlite3.connect(DOCUMENTS_DB_PATH)
            logger.info(f"Connected to database: {DOCUMENTS_DB_PATH}")
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
    
    def create_tables(self):
        """Create necessary tables if they don't exist"""
        try:
            cursor = self.conn.cursor()
            
            # Create documents table with status tracking
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL UNIQUE,
                filepath TEXT NOT NULL,
                status TEXT NOT NULL,
                trace_id TEXT,
                error_message TEXT,
                processed_date TIMESTAMP,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            self.conn.commit()
            logger.info("Database tables initialized")
        except sqlite3.Error as e:
            logger.error(f"Table creation error: {e}")
    
    def add_document(self, filename, filepath, status="pending", trace_id=None):
        """Add a document to the tracking database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO documents (filename, filepath, status, trace_id) VALUES (?, ?, ?, ?)",
                (filename, filepath, status, trace_id)
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error adding document to database: {e}")
            return False
    
    def update_document_status(self, filepath, status, error_message=None):
        """Update the status of a document in the database"""
        try:
            cursor = self.conn.cursor()
            if error_message:
                cursor.execute(
                    "UPDATE documents SET status = ?, error_message = ?, processed_date = ? WHERE filepath = ?",
                    (status, error_message, datetime.now(), filepath)
                )
            else:
                cursor.execute(
                    "UPDATE documents SET status = ?, processed_date = ? WHERE filepath = ?",
                    (status, datetime.now(), filepath)
                )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating document status: {e}")
            return False
    
    def get_document_status(self, filepath):
        """Get the status of a document"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT status FROM documents WHERE filepath = ?", 
                (filepath,)
            )
            result = cursor.fetchone()
            return result[0] if result else None
        except sqlite3.Error as e:
            logger.error(f"Error getting document status: {e}")
            return None
    
    def get_pending_documents(self):
        """Get all documents with 'pending' status"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT filepath FROM documents WHERE status = 'pending'")
            return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error getting pending documents: {e}")
            return []
    
    def flush_db(self, confirm=False):
        """
        Flush all data from the database.
        This is a destructive operation and requires confirmation.
        
        Args:
            confirm (bool): Confirmation flag to proceed with the flush
        
        Returns:
            bool: True if flush was successful, False otherwise
        """
        if not confirm:
            logger.warning("Flush operation requires confirmation. Set confirm=True to proceed.")
            return False
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM documents")
            self.conn.commit()
            logger.info("Database flushed successfully")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error flushing database: {e}")
            return False
    
    def get_all_documents(self, status=None):
        """
        Get all documents, optionally filtered by status.
        
        Args:
            status (str, optional): Filter by status (e.g., 'pending', 'processed', 'error')
        
        Returns:
            list: List of document records (as dictionaries)
        """
        try:
            cursor = self.conn.cursor()
            
            if status:
                cursor.execute(
                    """SELECT id, filename, filepath, status, error_message, 
                       processed_date, created_date FROM documents WHERE status = ?""", 
                    (status,)
                )
            else:
                cursor.execute(
                    """SELECT id, filename, filepath, status, error_message, 
                       processed_date, created_date FROM documents"""
                )
            
            columns = [desc[0] for desc in cursor.description]
            result = []
            
            for row in cursor.fetchall():
                result.append(dict(zip(columns, row)))
                
            return result
        except sqlite3.Error as e:
            logger.error(f"Error getting documents: {e}")
            return []
    
    def get_stats(self):
        """
        Get statistics about document processing.
        
        Returns:
            dict: Statistics about document counts by status
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT status, COUNT(*) as count FROM documents 
                GROUP BY status
            """)
            
            stats = {
                "total": 0,
                "pending": 0,
                "processing": 0,
                "processed": 0,
                "error": 0
            }
            
            for status, count in cursor.fetchall():
                stats[status] = count
                stats["total"] += count
                
            return stats
        except sqlite3.Error as e:
            logger.error(f"Error getting statistics: {e}")
            return {"error": str(e)}
            
    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
