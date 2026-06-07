import sqlite3
import pandas as pd
import duckdb
from typing import List, Dict, Any
from .base import BaseConverter

class SQLiteConverter(BaseConverter):
    def detect_tables(self) -> List[Dict[str, Any]]:
        tables = []
        try:
            conn = sqlite3.connect(self.file_path)
            cursor = conn.cursor()
            
            # Fetch all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            table_names = [row[0] for row in cursor.fetchall()]
            
            for table_name in table_names:
                # Fetch columns
                cursor.execute(f'PRAGMA table_info("{table_name}");')
                columns_info = cursor.fetchall()
                columns = [{"name": col[1], "type": col[2] or "TEXT"} for col in columns_info]
                
                # Fetch row count
                cursor.execute(f'SELECT COUNT(*) FROM "{table_name}";')
                row_count = cursor.fetchone()[0]
                
                tables.append({
                    "name": table_name,
                    "columns": columns,
                    "estimated_rows": row_count
                })
            
            conn.close()
        except Exception as e:
            # Return empty list or raise custom exception
            print(f"Error scanning SQLite file: {e}")
        return tables

    def get_preview(self, table_name: str, limit: int = 10) -> Dict[str, Any]:
        try:
            conn = sqlite3.connect(self.file_path)
            cursor = conn.cursor()
            
            # Fetch columns info
            cursor.execute(f'PRAGMA table_info("{table_name}");')
            columns = [col[1] for col in cursor.fetchall()]
            
            # Fetch rows
            cursor.execute(f'SELECT * FROM "{table_name}" LIMIT ?;', (limit,))
            rows = [list(row) for row in cursor.fetchall()]
            
            conn.close()
            return {
                "columns": columns,
                "rows": rows
            }
        except Exception as e:
            return {
                "columns": [],
                "rows": [],
                "error": str(e)
            }

    def convert(self, db_path: str, table_mappings: Dict[str, str]) -> List[str]:
        conn_sqlite = sqlite3.connect(self.file_path)
        cursor_sqlite = conn_sqlite.cursor()
        
        conn_duck = duckdb.connect(db_path)
        successful_tables = []
        
        # Try native ATTACH SQLite first
        try:
            conn_duck.execute("INSTALL sqlite; LOAD sqlite;")
            conn_duck.execute(f"ATTACH '{self.file_path}' AS sqlite_db (TYPE SQLITE);")
            
            for original_name, new_name in table_mappings.items():
                try:
                    conn_duck.execute(f'CREATE TABLE "{new_name}" AS SELECT * FROM sqlite_db."{original_name}";')
                    successful_tables.append(original_name)
                except Exception as table_err:
                    print(f"Error copying table {original_name} natively, will try fallback: {table_err}")
            
            conn_duck.execute("DETACH sqlite_db;")
        except Exception as native_err:
            print(f"Native SQLite scanner not available or failed: {native_err}. Falling back to Pandas streaming.")
            # Fallback to pandas streaming
            for original_name, new_name in table_mappings.items():
                if original_name in successful_tables:
                    continue
                try:
                    first = True
                    chunksize = 50000
                    # Read and insert chunk by chunk
                    for chunk in pd.read_sql_query(f'SELECT * FROM "{original_name}"', conn_sqlite, chunksize=chunksize):
                        conn_duck.register('temp_chunk', chunk)
                        if first:
                            conn_duck.execute(f'CREATE TABLE "{new_name}" AS SELECT * FROM temp_chunk')
                            first = False
                        else:
                            conn_duck.execute(f'INSERT INTO "{new_name}" SELECT * FROM temp_chunk')
                        conn_duck.unregister('temp_chunk')
                    successful_tables.append(original_name)
                except Exception as chunk_err:
                    print(f"Failed to copy table {original_name} using fallback: {chunk_err}")
        
        conn_sqlite.close()
        conn_duck.close()
        return successful_tables
