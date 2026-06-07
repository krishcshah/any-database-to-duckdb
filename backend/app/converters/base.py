from abc import ABC, abstractmethod
from typing import List, Dict, Any
import pandas as pd
import duckdb

class BaseConverter(ABC):
    def __init__(self, file_path: str):
        self.file_path = file_path

    @abstractmethod
    def detect_tables(self) -> List[Dict[str, Any]]:
        """
        Scan the file and return a list of dictionaries with table information:
        [
            {
                "name": str,
                "columns": [{"name": str, "type": str}],
                "estimated_rows": int
            }
        ]
        """
        pass

    @abstractmethod
    def get_preview(self, table_name: str, limit: int = 10) -> Dict[str, Any]:
        """
        Return the preview data for a table:
        {
            "columns": [str],
            "rows": [List[Any]]
        }
        """
        pass

    @abstractmethod
    def convert(self, db_path: str, table_mappings: Dict[str, str]) -> List[str]:
        """
        Write the tables to the target DuckDB database at db_path.
        table_mappings maps original table names to user-defined names.
        Returns a list of tables successfully written.
        """
        pass

    def _build_ocel_tables_from_parsed_data(
        self,
        conn_duck,
        event_attrs_map: Dict[str, Dict[str, str]],
        object_attrs_map: Dict[str, Dict[str, str]],
        events: List[Dict[str, Any]],
        objects: List[Dict[str, Any]],
        event_objects: List[Dict[str, Any]],
        object_objects: List[Dict[str, Any]],
        table_mappings: Dict[str, str] = None
    ):
        # 1. Fill discovered attributes and dynamic schemas
        discovered_events = {}
        for ev in events:
            ev_type = ev.get("type")
            if ev_type:
                if ev_type not in discovered_events:
                    discovered_events[ev_type] = set()
                for attr in ev.get("attributes", []) or []:
                    discovered_events[ev_type].add(attr.get("name"))
                    
        discovered_objects = {}
        for obj in objects:
            obj_type = obj.get("type")
            if obj_type:
                if obj_type not in discovered_objects:
                    discovered_objects[obj_type] = set()
                for attr in obj.get("attributes", []) or []:
                    discovered_objects[obj_type].add(attr.get("name"))
                    
        # Merge event types schema
        for ev_type, attrs in discovered_events.items():
            if ev_type not in event_attrs_map:
                event_attrs_map[ev_type] = {}
            for a in attrs:
                if a not in event_attrs_map[ev_type]:
                    event_attrs_map[ev_type][a] = "VARCHAR"
                    
        # Merge object types schema
        for obj_type, attrs in discovered_objects.items():
            if obj_type not in object_attrs_map:
                object_attrs_map[obj_type] = {}
            for a in attrs:
                if a not in object_attrs_map[obj_type]:
                    object_attrs_map[obj_type][a] = "VARCHAR"

        # 2. Populate metadata maps
        event_map_rows = []
        for ev_type in event_attrs_map:
            suffix = "".join(c.lower() for c in ev_type if c.isalnum())
            event_map_rows.append({"ocel_type": ev_type, "ocel_type_map": suffix})
            
        object_map_rows = []
        for obj_type in object_attrs_map:
            suffix = "".join(c.lower() for c in obj_type if c.isalnum())
            object_map_rows.append({"ocel_type": obj_type, "ocel_type_map": suffix})
            
        self._write_table(conn_duck, "event_map_type", ["ocel_type", "ocel_type_map"], {"ocel_type": "VARCHAR", "ocel_type_map": "VARCHAR"}, event_map_rows, table_mappings)
        self._write_table(conn_duck, "object_map_type", ["ocel_type", "ocel_type_map"], {"ocel_type": "VARCHAR", "ocel_type_map": "VARCHAR"}, object_map_rows, table_mappings)

        # 3. Populate core event and object tables
        event_rows = [{"ocel_id": ev.get("id"), "ocel_type": ev.get("type")} for ev in events if ev.get("id")]
        object_rows = [{"ocel_id": obj.get("id"), "ocel_type": obj.get("type")} for obj in objects if obj.get("id")]
        
        self._write_table(conn_duck, "event", ["ocel_id", "ocel_type"], {"ocel_id": "VARCHAR", "ocel_type": "VARCHAR"}, event_rows, table_mappings)
        self._write_table(conn_duck, "object", ["ocel_id", "ocel_type"], {"ocel_id": "VARCHAR", "ocel_type": "VARCHAR"}, object_rows, table_mappings)

        # 4. Populate relationships
        self._write_table(
            conn_duck,
            "event_object",
            ["ocel_event_id", "ocel_object_id", "ocel_qualifier"],
            {"ocel_event_id": "VARCHAR", "ocel_object_id": "VARCHAR", "ocel_qualifier": "VARCHAR"},
            event_objects,
            table_mappings
        )
        self._write_table(
            conn_duck,
            "object_object",
            ["ocel_source_id", "ocel_target_id", "ocel_qualifier"],
            {"ocel_source_id": "VARCHAR", "ocel_target_id": "VARCHAR", "ocel_qualifier": "VARCHAR"},
            object_objects,
            table_mappings
        )

        # 5. Dynamic event_<suffix> tables
        for ev_type, attrs in event_attrs_map.items():
            suffix = "".join(c.lower() for c in ev_type if c.isalnum())
            table_name = f"event_{suffix}"
            
            cols = ["ocel_id", "ocel_time"] + sorted(list(attrs.keys()))
            col_types = {"ocel_id": "VARCHAR", "ocel_time": "TIMESTAMP"}
            for name, t in attrs.items():
                col_types[name] = t
                
            type_rows = []
            for ev in events:
                if ev.get("type") == ev_type:
                    row = {
                        "ocel_id": ev.get("id"),
                        "ocel_time": ev.get("time")
                    }
                    for name in attrs:
                        row[name] = None
                    for attr in ev.get("attributes", []) or []:
                        name = attr.get("name")
                        val = attr.get("value")
                        if name in attrs:
                            row[name] = self._cast_value(val, col_types[name])
                    type_rows.append(row)
                    
            self._write_table(conn_duck, table_name, cols, col_types, type_rows, table_mappings)

        # 6. Dynamic object_<suffix> tables
        for obj_type, attrs in object_attrs_map.items():
            suffix = "".join(c.lower() for c in obj_type if c.isalnum())
            table_name = f"object_{suffix}"
            
            cols = ["ocel_id", "ocel_time", "ocel_changed_field"] + sorted(list(attrs.keys()))
            col_types = {"ocel_id": "VARCHAR", "ocel_time": "TIMESTAMP", "ocel_changed_field": "VARCHAR"}
            for name, t in attrs.items():
                col_types[name] = t
                
            type_rows = []
            for obj in objects:
                if obj.get("type") == obj_type:
                    obj_id = obj.get("id")
                    # Initial row
                    init_row = {
                        "ocel_id": obj_id,
                        "ocel_time": "1970-01-01T00:00:00Z",
                        "ocel_changed_field": None
                    }
                    for name in attrs:
                        init_row[name] = None
                    type_rows.append(init_row)
                    
                    # Row for each attribute entry
                    for attr in obj.get("attributes", []) or []:
                        name = attr.get("name")
                        val = attr.get("value")
                        time_str = attr.get("time") or "1970-01-01T00:00:00Z"
                        if name in attrs:
                            row = {
                                "ocel_id": obj_id,
                                "ocel_time": time_str,
                                "ocel_changed_field": name
                            }
                            for n in attrs:
                                row[n] = None
                            row[name] = self._cast_value(val, col_types[name])
                            type_rows.append(row)
                            
            self._write_table(conn_duck, table_name, cols, col_types, type_rows, table_mappings)

    def _write_table(self, conn_duck, table_name: str, cols: List[str], col_types: Dict[str, str], rows: List[Dict[str, Any]], table_mappings: Dict[str, str] = None):
        target_name = table_name
        if table_mappings and table_name in table_mappings:
            target_name = table_mappings[table_name]
            
        col_defs = []
        for col in cols:
            col_defs.append(f'"{col}" {col_types[col]}')
        schema_def = ", ".join(col_defs)
        
        table_exists = conn_duck.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name = '{target_name}'").fetchone()
        if not table_exists:
            conn_duck.execute(f'CREATE TABLE "{target_name}" ({schema_def});')
            
        if not rows:
            return
            
        df = pd.DataFrame(rows)
        for col in cols:
            if col not in df.columns:
                df[col] = None
                
        df = df[cols]
        
        for col in cols:
            if col_types[col] == "TIMESTAMP":
                df[col] = pd.to_datetime(df[col], errors='coerce')
            elif col_types[col] == "BOOLEAN":
                df[col] = df[col].apply(lambda x: True if str(x).strip() in ('1', 'true', 'True', 'yes', 'Yes') else (False if str(x).strip() in ('0', 'false', 'False', 'no', 'No') else None))
            elif col_types[col] == "BIGINT":
                df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')
            elif col_types[col] == "DOUBLE":
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
        conn_duck.register('temp_df', df)
        conn_duck.execute(f'INSERT INTO "{target_name}" SELECT * FROM temp_df;')
        conn_duck.unregister('temp_df')

    def _cast_value(self, val: Any, t: str) -> Any:
        if val is None:
            return None
        if t == "BOOLEAN":
            return True if str(val).strip() in ('1', 'true', 'True', 'yes', 'Yes') else False
        elif t == "BIGINT":
            try:
                return int(val)
            except ValueError:
                return None
        elif t == "DOUBLE":
            try:
                return float(val)
            except ValueError:
                return None
        else:
            return str(val)
