import sqlite3
import os
import time

class Database:
    def __init__(self, db_path="data/seen_items.db"):
        self.db_path = db_path
        # Assegurar que o directório existe
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()
        
    def _get_connection(self):
        return sqlite3.connect(self.db_path)
        
    def _init_db(self):
        """Cria a tabela se não existir."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS seen_items (
                    item_id TEXT PRIMARY KEY,
                    notified_at INTEGER
                )
            """)
            conn.commit()
            
    def is_item_seen(self, item_id: str) -> bool:
        """Verifica se um item já foi visto e guardado."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM seen_items WHERE item_id = ?", (str(item_id),))
            return cursor.fetchone() is not None
            
    def mark_item_seen(self, item_id: str):
        """Marca um item como visto gravando o seu ID com o timestamp actual."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = int(time.time())
            cursor.execute("""
                INSERT OR IGNORE INTO seen_items (item_id, notified_at) 
                VALUES (?, ?)
            """, (str(item_id), now))
            conn.commit()
            
    def prune_old_items(self, days_old=90):
        """
        Remove registos mais antigos do que `days_old` para manter a DB leve.
        Por omissão, 90 dias.
        """
        threshold = int(time.time()) - (days_old * 24 * 60 * 60)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM seen_items WHERE notified_at < ?", (threshold,))
            deleted = cursor.rowcount
            conn.commit()
            return deleted
