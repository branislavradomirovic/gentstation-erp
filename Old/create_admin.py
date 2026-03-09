import sqlite3
import hashlib

def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# Connect to your existing database
conn = sqlite3.connect('company.db')

# Define your credentials
admin_email = "admin@gentstation.com"
admin_password = "Admin123!"  # Change this after logging in
hashed_pw = hash_password(admin_password)

try:
    conn.execute("""
        INSERT INTO employees (name, surname, email, password, role) 
        VALUES ('System', 'Admin', ?, ?, 'General Manager')
    """, (admin_email, hashed_pw))
    conn.commit()
    print(f"✅ Admin created! Login: {admin_email} / Password: {admin_password}")
except Exception as e:
    print(f"❌ Error: {e} (User might already exist)")
finally:
    conn.close()