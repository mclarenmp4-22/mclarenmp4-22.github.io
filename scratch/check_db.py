import sqlite3
DB_PATH = r"c:\Users\trues\OneDrive\Desktop\Advaith\F1 Results database, upgraded\sessionresults.db"
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("SELECT Name, Championships, Wins FROM Drivers WHERE Name = 'Juan Manuel Fangio'")
print(cur.fetchone())
conn.close()
