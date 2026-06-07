import json
import pandas as pd
import duckdb
from typing import List, Dict, Any, Tuple
from .base import BaseConverter

class JSONConverter(BaseConverter):
    def _load_json_data(self) -> Any:
        with open(self.file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _is_ocel2(self) -> bool:
        try:
            data = self._load_json_data()
            if not isinstance(data, dict):
                return False
            return 'events' in data and 'objects' in data
        except Exception:
            return False

    def _map_json_type(self, t: str) -> str:
        t_lower = (t or "").lower()
        if t_lower == "integer":
            return "BIGINT"
        elif t_lower == "float":
            return "DOUBLE"
        elif t_lower == "boolean":
            return "BOOLEAN"
        elif t_lower == "time":
            return "TIMESTAMP"
        else:
            return "VARCHAR"

    def _parse_json_ocel2(self) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        data = self._load_json_data()
        
        event_attrs_map = {}
        object_attrs_map = {}
        events = []
        objects = []
        event_objects = []
        object_objects = []
        
        # 1. Parse declared eventTypes and objectTypes
        for et in data.get("eventTypes", []) or []:
            name = et.get("name")
            if name:
                event_attrs_map[name] = {a.get("name"): self._map_json_type(a.get("type")) for a in et.get("attributes", []) or []}
                
        for ot in data.get("objectTypes", []) or []:
            name = ot.get("name")
            if name:
                object_attrs_map[name] = {a.get("name"): self._map_json_type(a.get("type")) for a in ot.get("attributes", []) or []}
                
        # 2. Parse events
        events_raw = data.get("events", [])
        if isinstance(events_raw, dict):
            for ev_id, ev_val in events_raw.items():
                ev_type = ev_val.get("type")
                ev_time = ev_val.get("time")
                
                attrs_list = []
                attrs_raw = ev_val.get("attributes", {})
                if isinstance(attrs_raw, dict):
                    for k, v in attrs_raw.items():
                        attrs_list.append({"name": k, "value": v})
                elif isinstance(attrs_raw, list):
                    attrs_list = attrs_raw
                    
                events.append({
                    "id": ev_id,
                    "type": ev_type,
                    "time": ev_time,
                    "attributes": attrs_list
                })
                
                rels_raw = ev_val.get("relationships", []) or []
                if isinstance(rels_raw, list):
                    for rel in rels_raw:
                        obj_id = rel.get("objectId") or rel.get("object_id")
                        qualifier = rel.get("qualifier")
                        if ev_id and obj_id:
                            event_objects.append({
                                "ocel_event_id": ev_id,
                                "ocel_object_id": obj_id,
                                "ocel_qualifier": qualifier or ""
                            })
        elif isinstance(events_raw, list):
            for ev_val in events_raw:
                ev_id = ev_val.get("id")
                ev_type = ev_val.get("type")
                ev_time = ev_val.get("time")
                
                attrs_list = []
                attrs_raw = ev_val.get("attributes", [])
                if isinstance(attrs_raw, list):
                    attrs_list = attrs_raw
                elif isinstance(attrs_raw, dict):
                    for k, v in attrs_raw.items():
                        attrs_list.append({"name": k, "value": v})
                        
                events.append({
                    "id": ev_id,
                    "type": ev_type,
                    "time": ev_time,
                    "attributes": attrs_list
                })
                
                rels_raw = ev_val.get("relationships", []) or []
                if isinstance(rels_raw, list):
                    for rel in rels_raw:
                        obj_id = rel.get("objectId") or rel.get("object_id")
                        qualifier = rel.get("qualifier")
                        if ev_id and obj_id:
                            event_objects.append({
                                "ocel_event_id": ev_id,
                                "ocel_object_id": obj_id,
                                "ocel_qualifier": qualifier or ""
                            })
                            
        # 3. Parse objects
        objects_raw = data.get("objects", [])
        if isinstance(objects_raw, dict):
            for obj_id, obj_val in objects_raw.items():
                obj_type = obj_val.get("type")
                
                attrs_list = []
                attrs_raw = obj_val.get("attributes", {})
                if isinstance(attrs_raw, dict):
                    for k, v in attrs_raw.items():
                        if isinstance(v, list):
                            for entry in v:
                                attrs_list.append({
                                    "name": k,
                                    "value": entry.get("value"),
                                    "time": entry.get("time") or "1970-01-01T00:00:00Z"
                                })
                        else:
                            attrs_list.append({
                                "name": k,
                                "value": v,
                                "time": "1970-01-01T00:00:00Z"
                            })
                elif isinstance(attrs_raw, list):
                    attrs_list = attrs_raw
                    
                objects.append({
                    "id": obj_id,
                    "type": obj_type,
                    "attributes": attrs_list
                })
                
                rels_raw = obj_val.get("relationships", []) or []
                if isinstance(rels_raw, list):
                    for rel in rels_raw:
                        target_id = rel.get("objectId") or rel.get("object_id")
                        qualifier = rel.get("qualifier")
                        if obj_id and target_id:
                            object_objects.append({
                                "ocel_source_id": obj_id,
                                "ocel_target_id": target_id,
                                "ocel_qualifier": qualifier or ""
                            })
        elif isinstance(objects_raw, list):
            for obj_val in objects_raw:
                obj_id = obj_val.get("id")
                obj_type = obj_val.get("type")
                
                attrs_list = []
                attrs_raw = obj_val.get("attributes", [])
                if isinstance(attrs_raw, list):
                    attrs_list = attrs_raw
                elif isinstance(attrs_raw, dict):
                    for k, v in attrs_raw.items():
                        if isinstance(v, list):
                            for entry in v:
                                attrs_list.append({
                                    "name": k,
                                    "value": entry.get("value"),
                                    "time": entry.get("time") or "1970-01-01T00:00:00Z"
                                })
                        else:
                            attrs_list.append({
                                "name": k,
                                "value": v,
                                "time": "1970-01-01T00:00:00Z"
                            })
                            
                objects.append({
                    "id": obj_id,
                    "type": obj_type,
                    "attributes": attrs_list
                })
                
                rels_raw = obj_val.get("relationships", []) or []
                if isinstance(rels_raw, list):
                    for rel in rels_raw:
                        target_id = rel.get("objectId") or rel.get("object_id")
                        qualifier = rel.get("qualifier")
                        if obj_id and target_id:
                            object_objects.append({
                                "ocel_source_id": obj_id,
                                "ocel_target_id": target_id,
                                "ocel_qualifier": qualifier or ""
                            })
                            
        return event_attrs_map, object_attrs_map, events, objects, event_objects, object_objects

    def _detect_tables_from_data(self, data: Any) -> Dict[str, List[Dict[str, Any]]]:
        tables_data = {}
        if isinstance(data, list):
            if not data:
                tables_data["data"] = []
            elif isinstance(data[0], dict):
                tables_data["data"] = data
            else:
                tables_data["data"] = [{"value": val} for val in data]
        elif isinstance(data, dict):
            has_table_keys = False
            for key, val in data.items():
                if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                    tables_data[key] = val
                    has_table_keys = True
                elif isinstance(val, list) and len(val) > 0:
                    tables_data[key] = [{"value": item} for item in val]
                    has_table_keys = True
            
            if not has_table_keys:
                tables_data["data"] = [data]
        else:
            tables_data["data"] = [{"value": data}]
            
        return tables_data

    def detect_tables(self) -> List[Dict[str, Any]]:
        if self._is_ocel2():
            tables = []
            try:
                event_attrs_map, object_attrs_map, events, objects, event_objects, object_objects = self._parse_json_ocel2()
                
                # Discover attributes if not declared in map
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
                            
                # Merge event schemas
                for ev_type, attrs in discovered_events.items():
                    if ev_type not in event_attrs_map:
                        event_attrs_map[ev_type] = {}
                    for a in attrs:
                        if a not in event_attrs_map[ev_type]:
                            event_attrs_map[ev_type][a] = "VARCHAR"
                            
                # Merge object schemas
                for obj_type, attrs in discovered_objects.items():
                    if obj_type not in object_attrs_map:
                        object_attrs_map[obj_type] = {}
                    for a in attrs:
                        if a not in object_attrs_map[obj_type]:
                            object_attrs_map[obj_type][a] = "VARCHAR"

                # Core tables
                tables.extend([
                    {"name": "event_map_type", "columns": [{"name": "ocel_type", "type": "VARCHAR"}, {"name": "ocel_type_map", "type": "VARCHAR"}], "estimated_rows": len(event_attrs_map)},
                    {"name": "object_map_type", "columns": [{"name": "ocel_type", "type": "VARCHAR"}, {"name": "ocel_type_map", "type": "VARCHAR"}], "estimated_rows": len(object_attrs_map)},
                    {"name": "event", "columns": [{"name": "ocel_id", "type": "VARCHAR"}, {"name": "ocel_type", "type": "VARCHAR"}], "estimated_rows": len(events)},
                    {"name": "object", "columns": [{"name": "ocel_id", "type": "VARCHAR"}, {"name": "ocel_type", "type": "VARCHAR"}], "estimated_rows": len(objects)},
                    {"name": "event_object", "columns": [{"name": "ocel_event_id", "type": "VARCHAR"}, {"name": "ocel_object_id", "type": "VARCHAR"}, {"name": "ocel_qualifier", "type": "VARCHAR"}], "estimated_rows": len(event_objects)},
                    {"name": "object_object", "columns": [{"name": "ocel_source_id", "type": "VARCHAR"}, {"name": "ocel_target_id", "type": "VARCHAR"}, {"name": "ocel_qualifier", "type": "VARCHAR"}], "estimated_rows": len(object_objects)},
                ])
                
                # Dynamic event tables
                for ev_type, attrs in event_attrs_map.items():
                    suffix = "".join(c.lower() for c in ev_type if c.isalnum())
                    cols = [{"name": "ocel_id", "type": "VARCHAR"}, {"name": "ocel_time", "type": "TIMESTAMP"}]
                    for name, t in sorted(attrs.items()):
                        cols.append({"name": name, "type": t})
                    tables.append({"name": f"event_{suffix}", "columns": cols, "estimated_rows": len([e for e in events if e.get("type") == ev_type])})
                    
                # Dynamic object tables
                for obj_type, attrs in object_attrs_map.items():
                    suffix = "".join(c.lower() for c in obj_type if c.isalnum())
                    cols = [{"name": "ocel_id", "type": "VARCHAR"}, {"name": "ocel_time", "type": "TIMESTAMP"}, {"name": "ocel_changed_field", "type": "VARCHAR"}]
                    for name, t in sorted(attrs.items()):
                        cols.append({"name": name, "type": t})
                    row_count = sum(1 + len(o.get("attributes", []) or []) for o in objects if o.get("type") == obj_type)
                    tables.append({"name": f"object_{suffix}", "columns": cols, "estimated_rows": row_count})
                    
            except Exception as e:
                print(f"Error scanning OCEL2 JSON: {e}")
            return tables
        else:
            tables = []
            try:
                data = self._load_json_data()
                tables_data = self._detect_tables_from_data(data)
                
                for table_name, rows in tables_data.items():
                    if not rows:
                        tables.append({
                            "name": table_name,
                            "columns": [],
                            "estimated_rows": 0
                        })
                        continue
                    
                    sample_df = pd.json_normalize(rows[:100], sep='_')
                    columns = []
                    for col in sample_df.columns:
                        col_type = "TEXT"
                        dtype = sample_df[col].dtype
                        if pd.api.types.is_integer_dtype(dtype):
                            col_type = "BIGINT"
                        elif pd.api.types.is_float_dtype(dtype):
                            col_type = "DOUBLE"
                        elif pd.api.types.is_bool_dtype(dtype):
                            col_type = "BOOLEAN"
                        columns.append({"name": col, "type": col_type})
                    
                    tables.append({
                        "name": table_name,
                        "columns": columns,
                        "estimated_rows": len(rows)
                    })
            except Exception as e:
                print(f"Error scanning JSON file: {e}")
            return tables

    def get_preview(self, table_name: str, limit: int = 10) -> Dict[str, Any]:
        if self._is_ocel2():
            try:
                event_attrs_map, object_attrs_map, events, objects, event_objects, object_objects = self._parse_json_ocel2()
                conn = duckdb.connect(":memory:")
                self._build_ocel_tables_from_parsed_data(conn, event_attrs_map, object_attrs_map, events, objects, event_objects, object_objects)
                
                table_exists = conn.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name = '{table_name}'").fetchone()
                if not table_exists:
                    conn.close()
                    return {"columns": [], "rows": [], "error": f"Table '{table_name}' not found."}
                    
                cols_info = conn.execute(f'PRAGMA table_info("{table_name}");').fetchall()
                columns = [c[1] for c in cols_info]
                
                rows = conn.execute(f'SELECT * FROM "{table_name}" LIMIT ?;', (limit,)).fetchall()
                
                formatted_rows = []
                for r in rows:
                    row_list = []
                    for val in r:
                        if pd.isnull(val):
                            row_list.append(None)
                        elif isinstance(val, bool):
                            row_list.append(val)
                        elif hasattr(val, 'isoformat'):
                            row_list.append(val.isoformat())
                        else:
                            row_list.append(val)
                    formatted_rows.append(row_list)
                    
                conn.close()
                return {
                    "columns": columns,
                    "rows": formatted_rows
                }
            except Exception as e:
                return {"columns": [], "rows": [], "error": str(e)}
        else:
            try:
                data = self._load_json_data()
                tables_data = self._detect_tables_from_data(data)
                
                if table_name not in tables_data:
                    return {"columns": [], "rows": [], "error": f"Table '{table_name}' not found."}
                    
                rows = tables_data[table_name]
                if not rows:
                    return {"columns": [], "rows": []}
                    
                df = pd.json_normalize(rows[:limit], sep='_')
                columns = list(df.columns)
                
                formatted_rows = df.where(pd.notnull(df), None).values.tolist()
                
                return {
                    "columns": columns,
                    "rows": formatted_rows
                }
            except Exception as e:
                return {
                    "columns": [],
                    "rows": [],
                    "error": str(e)
                }

    def convert(self, db_path: str, table_mappings: Dict[str, str]) -> List[str]:
        if self._is_ocel2():
            try:
                event_attrs_map, object_attrs_map, events, objects, event_objects, object_objects = self._parse_json_ocel2()
                conn_duck = duckdb.connect(db_path)
                
                self._build_ocel_tables_from_parsed_data(
                    conn_duck,
                    event_attrs_map,
                    object_attrs_map,
                    events,
                    objects,
                    event_objects,
                    object_objects,
                    table_mappings
                )
                
                successful_tables = []
                for original_name, new_name in table_mappings.items():
                    table_exists = conn_duck.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name = '{new_name}'").fetchone()
                    if table_exists:
                        successful_tables.append(original_name)
                        
                conn_duck.close()
                return successful_tables
            except Exception as e:
                print(f"Error during OCEL2 JSON conversion: {e}")
                return []
        else:
            data = self._load_json_data()
            tables_data = self._detect_tables_from_data(data)
            
            conn_duck = duckdb.connect(db_path)
            successful_tables = []
            
            for original_name, new_name in table_mappings.items():
                if original_name not in tables_data:
                    continue
                try:
                    rows = tables_data[original_name]
                    if not rows:
                        table_exists = conn_duck.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name = '{new_name}'").fetchone()
                        if not table_exists:
                            conn_duck.execute(f'CREATE TABLE "{new_name}" (data TEXT);')
                        successful_tables.append(original_name)
                        continue
                    
                    df = pd.json_normalize(rows, sep='_')
                    
                    for col in df.columns:
                        if df[col].apply(lambda x: isinstance(x, (list, dict))).any():
                            df[col] = df[col].apply(lambda x: json.dumps(x) if isinstance(x, (list, dict)) else x)
                    
                    conn_duck.register('temp_df', df)
                    table_exists = conn_duck.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name = '{new_name}'").fetchone()
                    if table_exists:
                        conn_duck.execute(f'INSERT INTO "{new_name}" SELECT * FROM temp_df;')
                    else:
                        conn_duck.execute(f'CREATE TABLE "{new_name}" AS SELECT * FROM temp_df;')
                    conn_duck.unregister('temp_df')
                    successful_tables.append(original_name)
                except Exception as err:
                    print(f"Failed to copy JSON table {original_name}: {err}")
                    
            conn_duck.close()
            return successful_tables
