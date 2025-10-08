import os
import psycopg2
from datetime import datetime
import logging

class FuelDatabase:
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        self.init_db()
    
    def get_connection(self):
        return psycopg2.connect(self.database_url)
    
    def init_db(self):
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS refills
                         (id SERIAL PRIMARY KEY,
                          user_id BIGINT, 
                          timestamp TEXT,
                          amount REAL, 
                          cost REAL, 
                          odometer INTEGER)''')
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Database init error: {e}")
    
    def add_refill(self, user_id, amount, cost, odometer):
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("INSERT INTO refills (user_id, timestamp, amount, cost, odometer) VALUES (%s, %s, %s, %s, %s)",
                     (user_id, datetime.now().isoformat(), amount, cost, odometer))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Add refill error: {e}")
            return False
    
    def get_current_consumption(self, user_id):
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM refills WHERE user_id = %s ORDER BY odometer DESC LIMIT 2", (user_id,))
            refills = c.fetchall()
            conn.close()
            
            if len(refills) < 2:
                return None
            
            latest = refills[0]  # [id, user_id, timestamp, amount, cost, odometer]
            previous = refills[1]
            
            distance = latest[5] - previous[5]
            fuel_used = previous[3]
            
            if distance > 0:
                consumption = (fuel_used / distance) * 100
                return {
                    'consumption': f"{consumption:.1f}",
                    'distance': distance,
                    'fuel_used': fuel_used
                }
        except Exception as e:
            logging.error(f"Get consumption error: {e}")
        return None
    
    def get_monthly_statistics(self, user_id):
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute('''SELECT 
                        TO_CHAR(TO_DATE(timestamp, 'YYYY-MM-DD"T"HH24:MI:SS.MS'), 'Month YYYY') as month,
                        SUM(amount) as total_liters,
                        SUM(cost) as total_cost,
                        AVG(cost/amount) as avg_price
                        FROM refills 
                        WHERE user_id = %s 
                        GROUP BY TO_CHAR(TO_DATE(timestamp, 'YYYY-MM-DD"T"HH24:MI:SS.MS'), 'Month YYYY')
                        ORDER BY MIN(TO_DATE(timestamp, 'YYYY-MM-DD"T"HH24:MI:SS.MS')) DESC''', (user_id,))
            
            results = []
            for row in c.fetchall():
                results.append({
                    'month': row[0].strip(),
                    'liters': f"{row[1]:.1f}",
                    'cost': f"{row[2]:.0f}",
                    'avg_price_per_liter': f"{row[3]:.1f}" if row[3] else "0.0"
                })
            conn.close()
            return results
        except Exception as e:
            logging.error(f"Monthly stats error: {e}")
            return []
    
    def get_user_refills(self, user_id, limit=10):
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM refills WHERE user_id = %s ORDER BY timestamp DESC LIMIT %s", (user_id, limit))
            refills = []
            for row in c.fetchall():
                refills.append({
                    'timestamp': row[2],
                    'amount': row[3],
                    'cost': row[4],
                    'odometer': row[5]
                })
            conn.close()
            return refills
        except Exception as e:
            logging.error(f"Get refills error: {e}")
            return []
    
    def delete_user_data(self, user_id):
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("DELETE FROM refills WHERE user_id = %s", (user_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Delete error: {e}")
            return False
