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

    def _is_ocel2(self) -> bool:
        try:
            conn = sqlite3.connect(self.file_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row[0] for row in cursor.fetchall()}
            conn.close()
            required = {"event", "object", "event_object", "event_map_type", "object_map_type"}
            return required.issubset(tables)
        except Exception:
            return False

    def _sqlite_discover_event_attrs(self, cur) -> list:
        cur.execute("SELECT ocel_type_map FROM event_map_type")
        activities = [row[0] for row in cur.fetchall()]
        cols = set()
        for act in activities:
            table = f"event_{act}"
            try:
                cur.execute(f"PRAGMA table_info('{table}')")
                for row in cur.fetchall():
                    col_name = row[1]
                    if col_name not in ("ocel_id", "ocel_time"):
                        cols.add(col_name)
            except Exception:
                pass
        return sorted(list(cols))

    def _sqlite_discover_obj_attrs(self, cur) -> list:
        cur.execute("SELECT ocel_type_map FROM object_map_type")
        obj_types = [row[0] for row in row or []] if False else [row[0] for row in cur.fetchall()]
        cols = set()
        for ot in obj_types:
            table = f"object_{ot}"
            try:
                cur.execute(f"PRAGMA table_info('{table}')")
                for row in cur.fetchall():
                    col_name = row[1]
                    if col_name not in ("ocel_id", "ocel_time"):
                        cols.add(col_name)
            except Exception:
                pass
        return sorted(list(cols))

    def _create_flat_schema(self, conn_duck, event_attr_cols, obj_attr_cols):
        event_attr_defs = "".join(f',\n    "{c}" VARCHAR' for c in event_attr_cols)
        obj_attr_defs = "".join(f',\n    "{c}" VARCHAR' for c in obj_attr_cols)

        conn_duck.execute(f"""
            CREATE TABLE IF NOT EXISTS events (
                event_id       VARCHAR PRIMARY KEY,
                activity       VARCHAR NOT NULL,
                timestamp_unix BIGINT  NOT NULL
                {event_attr_defs}
            )
        """)

        conn_duck.execute(f"""
            CREATE TABLE IF NOT EXISTS objects (
                obj_id   VARCHAR PRIMARY KEY,
                obj_type VARCHAR NOT NULL
                {obj_attr_defs}
            )
        """)

        conn_duck.execute("""
            CREATE TABLE IF NOT EXISTS event_object (
                event_id  VARCHAR NOT NULL,
                obj_id    VARCHAR NOT NULL,
                qualifier VARCHAR,
                PRIMARY KEY (event_id, obj_id)
            )
        """)

        conn_duck.execute(f"""
            CREATE TABLE IF NOT EXISTS object_attribute_history (
                obj_id         VARCHAR NOT NULL,
                timestamp_unix BIGINT  NOT NULL{obj_attr_defs},
                PRIMARY KEY (obj_id, timestamp_unix)
            )
        """)

        conn_duck.execute("""
            CREATE TABLE IF NOT EXISTS object_relations (
                source_obj_id VARCHAR NOT NULL,
                target_obj_id VARCHAR NOT NULL,
                qualifier     VARCHAR,
                PRIMARY KEY (source_obj_id, target_obj_id)
            )
        """)

        conn_duck.execute("CREATE INDEX IF NOT EXISTS idx_event_object_obj ON event_object(obj_id)")
        conn_duck.execute("CREATE INDEX IF NOT EXISTS idx_event_object_ev  ON event_object(event_id)")
        conn_duck.execute("CREATE INDEX IF NOT EXISTS idx_objects_type     ON objects(obj_type)")
        conn_duck.execute("CREATE INDEX IF NOT EXISTS idx_events_ts        ON events(timestamp_unix)")
        if obj_attr_cols:
            conn_duck.execute("CREATE INDEX IF NOT EXISTS idx_obj_hist_obj ON object_attribute_history(obj_id)")

    def _convert_ocel2(self, conn_duck):
        import os
        con_sqlite = sqlite3.connect(self.file_path)
        cur_sqlite = con_sqlite.cursor()
        
        event_attr_cols = self._sqlite_discover_event_attrs(cur_sqlite)
        obj_attr_cols = self._sqlite_discover_obj_attrs(cur_sqlite)
        
        cur_sqlite.execute("SELECT ocel_type_map FROM event_map_type")
        activities = [row[0] for row in cur_sqlite.fetchall()]

        cur_sqlite.execute("SELECT ocel_type_map FROM object_map_type")
        obj_types = [row[0] for row in cur_sqlite.fetchall()]
        
        act_cols_map = {}
        for act in activities:
            try:
                cur_sqlite.execute(f"PRAGMA table_info('event_{act}')")
                act_cols_map[act] = {row[1] for row in cur_sqlite.fetchall()} - {"ocel_id", "ocel_time"}
            except Exception:
                act_cols_map[act] = set()

        type_cols_map = {}
        for ot in obj_types:
            try:
                cur_sqlite.execute(f"PRAGMA table_info('object_{ot}')")
                type_cols_map[ot] = [row[1] for row in cur_sqlite.fetchall() if row[1] not in ("ocel_id", "ocel_time")]
            except Exception:
                type_cols_map[ot] = []

        con_sqlite.close()

        # Create flat schema
        self._create_flat_schema(conn_duck, event_attr_cols, obj_attr_cols)

        abs_path = os.path.abspath(self.file_path)
        conn_duck.execute("SET sqlite_all_varchar = true")
        conn_duck.execute(f"ATTACH '{abs_path}' AS src (TYPE sqlite)")
        
        # 1. Populate events table
        if activities:
            ts_parts = []
            for act in activities:
                table = f"event_{act}"
                act_cols = act_cols_map[act]
                attr_selects = ", ".join(
                    f'"{c}"::VARCHAR AS "{c}"' if c in act_cols else f'NULL::VARCHAR AS "{c}"'
                    for c in event_attr_cols
                )
                attr_part = (", " + attr_selects) if event_attr_cols else ""
                ts_parts.append(f'SELECT ocel_id, ocel_time{attr_part} FROM src."{table}"')

            ts_union = " UNION ALL ".join(ts_parts)
            conn_duck.execute(f"CREATE TEMP TABLE _ev_ts AS SELECT DISTINCT ON (ocel_id) * FROM ({ts_union}) ORDER BY ocel_id, ocel_time DESC")

            attr_sel = (
                ", " + ", ".join(f'ts."{c}"' for c in event_attr_cols)
            ) if event_attr_cols else ""

            conn_duck.execute(f"""
                INSERT OR IGNORE INTO events
                SELECT e.ocel_id                                        AS event_id,
                       emt.ocel_type_map                                AS activity,
                       epoch(CAST(ts.ocel_time AS TIMESTAMPTZ))::BIGINT AS timestamp_unix
                       {attr_sel}
                FROM src.event e
                JOIN src.event_map_type emt ON e.ocel_type = emt.ocel_type
                JOIN _ev_ts ts              ON e.ocel_id   = ts.ocel_id
            """)
            conn_duck.execute("DROP TABLE _ev_ts")

        # 2. Populate event_object table
        conn_duck.execute(f"""
            INSERT OR IGNORE INTO event_object
            SELECT ocel_event_id AS event_id, ocel_object_id AS obj_id, MIN(ocel_qualifier) AS qualifier
            FROM src.event_object
            GROUP BY ocel_event_id, ocel_object_id
        """)

        # 3. Populate object_relations table
        try:
            conn_duck.execute(f"""
                INSERT OR IGNORE INTO object_relations
                SELECT ocel_source_id AS source_obj_id, ocel_target_id AS target_obj_id, MIN(ocel_qualifier) AS qualifier
                FROM src.object_object
                GROUP BY ocel_source_id, ocel_target_id
            """)
        except Exception:
            pass

        # 4. Populate objects table (latest attributes) and history table
        latest_attrs = {}
        snapshot_map = {}
        
        def parse_ts(ts_str: str) -> int:
            if not ts_str:
                return 0
            from datetime import datetime, timezone
            for fmt in (
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ):
                try:
                    dt = datetime.strptime(ts_str, fmt)
                    return int(dt.replace(tzinfo=timezone.utc).timestamp())
                except ValueError:
                    continue
            return 0

        for ot in obj_types:
            table = f"object_{ot}"
            tbl_cols = type_cols_map[ot]
            if not tbl_cols:
                continue
            col_select = ", ".join(['"ocel_id"', '"ocel_time"'] + [f'"{c}"' for c in tbl_cols])
            try:
                df = conn_duck.execute(f'SELECT {col_select} FROM src."{table}" ORDER BY ocel_time').df()
                for idx, row in df.iterrows():
                    obj_id = str(row["ocel_id"])
                    ts_str = str(row["ocel_time"]) if pd.notnull(row["ocel_time"]) else ""
                    ts_unix = parse_ts(ts_str)
                    attrs = {c: str(row[c]) for c in tbl_cols if pd.notnull(row[c])}
                    latest_attrs.setdefault(obj_id, {}).update(attrs)
                    if obj_attr_cols and attrs:
                        snapshot_map.setdefault((obj_id, ts_unix), {}).update(attrs)
            except Exception:
                pass

        id_type_df = conn_duck.execute("""
            SELECT o.ocel_id, emt.ocel_type_map
            FROM src.object o
            JOIN src.object_map_type emt ON o.ocel_type = emt.ocel_type
        """).df()

        obj_ids_list = id_type_df["ocel_id"].tolist()
        obj_types_list = id_type_df["ocel_type_map"].tolist()
        
        obj_attr_data = {c: [] for c in obj_attr_cols}
        for obj_id in obj_ids_list:
            latest = latest_attrs.get(obj_id, {})
            for c in obj_attr_cols:
                obj_attr_data[c].append(latest.get(c))

        objects_df = pd.DataFrame({
            "obj_id": obj_ids_list,
            "obj_type": obj_types_list,
            **{c: obj_attr_data[c] for c in obj_attr_cols}
        })
        objects_df = objects_df.drop_duplicates(subset=['obj_id'])
        
        conn_duck.register('temp_objects', objects_df)
        conn_duck.execute("INSERT OR IGNORE INTO objects SELECT * FROM temp_objects")
        conn_duck.unregister('temp_objects')

        if obj_attr_cols and snapshot_map:
            hist_obj_ids = []
            hist_ts = []
            hist_attr = {c: [] for c in obj_attr_cols}
            for (obj_id, ts_unix), attrs in snapshot_map.items():
                hist_obj_ids.append(obj_id)
                hist_ts.append(ts_unix)
                for c in obj_attr_cols:
                    hist_attr[c].append(attrs.get(c))
            
            hist_df = pd.DataFrame({
                "obj_id": hist_obj_ids,
                "timestamp_unix": hist_ts,
                **{c: hist_attr[c] for c in obj_attr_cols}
            })
            
            conn_duck.register('temp_history', hist_df)
            conn_duck.execute("INSERT OR IGNORE INTO object_attribute_history SELECT * FROM temp_history")
            conn_duck.unregister('temp_history')

        conn_duck.execute("DETACH src")

    def convert(self, db_path: str, table_mappings: Dict[str, str]) -> List[str]:
        conn_sqlite = sqlite3.connect(self.file_path)
        cursor_sqlite = conn_sqlite.cursor()
        
        conn_duck = duckdb.connect(db_path)
        successful_tables = []
        
        if self._is_ocel2():
            try:
                self._convert_ocel2(conn_duck)
            except Exception as e:
                print(f"Error during SQLite OCEL 2.0 flat conversion: {e}")
        
        # Try native ATTACH SQLite first
        try:
            conn_duck.execute("INSTALL sqlite; LOAD sqlite;")
            conn_duck.execute(f"ATTACH '{self.file_path}' AS sqlite_db (TYPE SQLITE);")
            
            for original_name, new_name in table_mappings.items():
                if original_name == "event_object" and new_name == "event_object":
                    successful_tables.append(original_name)
                    continue
                # Check if table exists in DuckDB (using current_database() to ignore tables in attached databases)
                table_exists = conn_duck.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name = '{new_name}' AND table_catalog = current_database()").fetchone()
                if table_exists:
                    conn_duck.execute(f'INSERT INTO "{new_name}" SELECT * FROM sqlite_db."{original_name}";')
                else:
                    conn_duck.execute(f'CREATE TABLE "{new_name}" AS SELECT * FROM sqlite_db."{original_name}";')
                successful_tables.append(original_name)
            
            conn_duck.execute("DETACH sqlite_db;")
        except Exception as native_err:
            print(f"Native SQLite scanner not available or failed: {native_err}. Falling back to Pandas streaming.")
            try:
                conn_duck.execute("DETACH sqlite_db;")
            except Exception:
                pass
            # Fallback to pandas streaming
            for original_name, new_name in table_mappings.items():
                if original_name in successful_tables:
                    continue
                if original_name == "event_object" and new_name == "event_object":
                    successful_tables.append(original_name)
                    continue
                try:
                    table_exists = conn_duck.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name = '{new_name}' AND table_catalog = current_database()").fetchone()
                    first = not table_exists
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
