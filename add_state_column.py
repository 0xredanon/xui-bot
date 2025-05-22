import mysql.connector
import os
import sys
from dotenv import load_dotenv
from proj import *

# Load environment variables
load_dotenv()

# Get database credentials from environment or use defaults
DB_HOST = DB_HOST
DB_USER = DB_USER
DB_PASS = DB_PASSWORD
DB_NAME = DB_NAME

def add_state_column():
    """Add state column to telegram_users table"""
    try:
        # Connect to the database
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME
        )
        
        cursor = conn.cursor()
        
        # Check if the column already exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'telegram_users' 
            AND column_name = 'state'
            AND table_schema = %s
        """, (DB_NAME,))
        
        if cursor.fetchone():
            print("State column already exists in telegram_users table")
            return True
        
        # Add the column
        cursor.execute("""
            ALTER TABLE telegram_users
            ADD COLUMN state VARCHAR(255) NULL
        """)
        
        conn.commit()
        print("Successfully added state column to telegram_users table")
        
        # Close the connection
        cursor.close()
        conn.close()
        
        return True
            
    except Exception as e:
        print(f"Error adding state column: {str(e)}")
        return False

if __name__ == "__main__":
    # Run the function
    if add_state_column():
        print("Migration completed successfully")
        sys.exit(0)
    else:
        print("Migration failed")
        sys.exit(1) 