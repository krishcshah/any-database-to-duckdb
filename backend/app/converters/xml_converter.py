import xml.etree.ElementTree as ET
import pandas as pd
import duckdb
import os
from typing import List, Dict, Any, Tuple, Set
from .base import BaseConverter

class XMLConverter(BaseConverter):
    def __init__(self, file_path: str):
        super().__init__(file_path)
        self.tables_data: Dict[str, List[Dict[str, Any]]] = {}
        self.table_schemas: Dict[str, List[Dict[str, str]]] = {}
        self._parsed = False

    def _is_ocel2(self) -> bool:
        try:
            tree = ET.parse(self.file_path)
            root = tree.getroot()
            tag = root.tag.split('}')[-1]
            if tag != 'log':
                return False
            child_tags = {child.tag.split('}')[-1] for child in root}
            return 'events' in child_tags and 'objects' in child_tags
        except Exception:
            return False

    def _map_xml_type(self, t: str) -> str:
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

    def _parse_xml_ocel2(self) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        tree = ET.parse(self.file_path)
        root = tree.getroot()
        
        event_attrs_map = {}
        object_attrs_map = {}
        events = []
        objects = []
        event_objects = []
        object_objects = []
        
        def clean(tag):
            return tag.split('}')[-1]
            
        for child in root:
            tag = clean(child.tag)
            if tag == 'event-types':
                for et in child:
                    et_name = et.attrib.get('name')
                    if et_name:
                        event_attrs_map[et_name] = {}
                        attrs_elem = et.find('{*}attributes')
                        if attrs_elem is None:
                            attrs_elem = et.find('attributes')
                        if attrs_elem is not None:
                            for attr in attrs_elem:
                                attr_name = attr.attrib.get('name')
                                attr_type = attr.attrib.get('type')
                                if attr_name:
                                    event_attrs_map[et_name][attr_name] = self._map_xml_type(attr_type)
            elif tag == 'object-types':
                for ot in child:
                    ot_name = ot.attrib.get('name')
                    if ot_name:
                        object_attrs_map[ot_name] = {}
                        attrs_elem = ot.find('{*}attributes')
                        if attrs_elem is None:
                            attrs_elem = ot.find('attributes')
                        if attrs_elem is not None:
                            for attr in attrs_elem:
                                attr_name = attr.attrib.get('name')
                                attr_type = attr.attrib.get('type')
                                if attr_name:
                                    object_attrs_map[ot_name][attr_name] = self._map_xml_type(attr_type)
            elif tag == 'events':
                for ev in child:
                    if clean(ev.tag) == 'event':
                        ev_id = ev.attrib.get('id')
                        ev_type = ev.attrib.get('type')
                        ev_time = ev.attrib.get('time')
                        
                        event_entry = {
                            "id": ev_id,
                            "type": ev_type,
                            "time": ev_time,
                            "attributes": []
                        }
                        
                        attrs_elem = ev.find('{*}attributes')
                        if attrs_elem is None:
                            attrs_elem = ev.find('attributes')
                        if attrs_elem is not None:
                            for attr in attrs_elem:
                                attr_name = attr.attrib.get('name')
                                attr_val = attr.text.strip() if attr.text else ""
                                if attr_name:
                                    event_entry["attributes"].append({"name": attr_name, "value": attr_val})
                                    
                        objs_elem = ev.find('{*}objects')
                        if objs_elem is None:
                            objs_elem = ev.find('objects')
                        if objs_elem is not None:
                            for rel in objs_elem:
                                rel_tag = clean(rel.tag)
                                if rel_tag in ('relobj', 'relationship'):
                                    obj_id = rel.attrib.get('object-id') or rel.attrib.get('objectId') or rel.attrib.get('object_id')
                                    qualifier = rel.attrib.get('qualifier') or rel.attrib.get('relationship')
                                    if ev_id and obj_id:
                                        event_objects.append({
                                            "ocel_event_id": ev_id,
                                            "ocel_object_id": obj_id,
                                            "ocel_qualifier": qualifier or ""
                                        })
                        events.append(event_entry)
                        
            elif tag == 'objects':
                for obj in child:
                    if clean(obj.tag) == 'object':
                        obj_id = obj.attrib.get('id')
                        obj_type = obj.attrib.get('type')
                        
                        object_entry = {
                            "id": obj_id,
                            "type": obj_type,
                            "attributes": [],
                            "relationships": []
                        }
                        
                        attrs_elem = obj.find('{*}attributes')
                        if attrs_elem is None:
                            attrs_elem = obj.find('attributes')
                        if attrs_elem is not None:
                            for attr in attrs_elem:
                                attr_name = attr.attrib.get('name')
                                attr_time = attr.attrib.get('time')
                                attr_val = attr.text.strip() if attr.text else ""
                                if attr_name:
                                    object_entry["attributes"].append({
                                        "name": attr_name,
                                        "value": attr_val,
                                        "time": attr_time or "1970-01-01T00:00:00Z"
                                    })
                                    
                        objs_elem = obj.find('{*}objects')
                        if objs_elem is None:
                            objs_elem = obj.find('objects')
                        if objs_elem is not None:
                            for rel in objs_elem:
                                rel_tag = clean(rel.tag)
                                if rel_tag in ('relobj', 'relationship'):
                                    target_id = rel.attrib.get('object-id') or rel.attrib.get('objectId') or rel.attrib.get('object_id')
                                    qualifier = rel.attrib.get('qualifier') or rel.attrib.get('relationship')
                                    if obj_id and target_id:
                                        object_objects.append({
                                            "ocel_source_id": obj_id,
                                            "ocel_target_id": target_id,
                                            "ocel_qualifier": qualifier or ""
                                        })
                        objects.append(object_entry)
                        
        return event_attrs_map, object_attrs_map, events, objects, event_objects, object_objects

    def _parse_xml(self):
        if self._parsed:
            return
        
        try:
            tree = ET.parse(self.file_path)
            root = tree.getroot()
        except Exception as e:
            print(f"Error parsing XML: {e}")
            self._parsed = True
            return

        element_ids = {}
        path_counts = {}
        table_paths: Set[Tuple[str, ...]] = set()
        
        id_counter = 0
        
        def analyze_node(node: ET.Element, path: Tuple[str, ...]):
            nonlocal id_counter
            id_counter += 1
            element_ids[node] = id_counter
            
            path_counts[path] = path_counts.get(path, 0) + 1
            
            child_counts = {}
            for child in node:
                child_counts[child.tag] = child_counts.get(child.tag, 0) + 1
            
            for child_tag, count in child_counts.items():
                if count > 1:
                    table_paths.add(path + (child_tag,))
            
            for child in node:
                child_path = path + (child.tag,)
                analyze_node(child, child_path)

        root_path = (root.tag,)
        
        for child in root:
            table_paths.add((root.tag, child.tag))
            
        analyze_node(root, root_path)

        path_to_tablename = {}
        used_names = set()
        for path in table_paths:
            name = path[-1]
            if name in used_names:
                name = "_".join(path[1:])
            used_names.add(name)
            path_to_tablename[path] = name

        self.tables_data = {name: [] for name in path_to_tablename.values()}

        def extract_text(node: ET.Element) -> str:
            parts = []
            if node.text and node.text.strip():
                parts.append(node.text.strip())
            for child in node:
                parts.append(extract_text(child))
                if child.tail and child.tail.strip():
                    parts.append(child.tail.strip())
            return " ".join(parts).strip()

        def extract_data(node: ET.Element, path: Tuple[str, ...], closest_table_parent_id: Any, closest_table_parent_tag: str):
            node_id = element_ids[node]
            
            is_table = path in table_paths
            current_table_id = closest_table_parent_id
            current_table_tag = closest_table_parent_tag
            
            if is_table:
                table_name = path_to_tablename[path]
                row = {
                    "_id": node_id
                }
                if closest_table_parent_id is not None:
                    row[f"_parent_{closest_table_parent_tag}_id"] = closest_table_parent_id
                
                for attr_name, attr_val in node.attrib.items():
                    row[attr_name] = attr_val
                
                if node.text and node.text.strip() and len(node) == 0:
                    row["value"] = node.text.strip()
                
                for child in node:
                    child_path = path + (child.tag,)
                    if child_path not in table_paths:
                        child_text = extract_text(child)
                        if child_text:
                            if child.tag in row:
                                row[child.tag] = f"{row[child.tag]}; {child_text}"
                            else:
                                row[child.tag] = child_text
                
                self.tables_data[table_name].append(row)
                current_table_id = node_id
                current_table_tag = table_name

            for child in node:
                child_path = path + (child.tag,)
                extract_data(child, child_path, current_table_id, current_table_tag)

        extract_data(root, root_path, None, "")

        self.table_schemas = {}
        for table_name, rows in self.tables_data.items():
            if not rows:
                self.table_schemas[table_name] = []
                continue
            
            df = pd.DataFrame(rows)
            columns = []
            for col in df.columns:
                col_type = "TEXT"
                dtype = df[col].dtype
                if col in ("_id",) or col.startswith("_parent_"):
                    col_type = "BIGINT"
                elif pd.api.types.is_integer_dtype(dtype):
                    col_type = "BIGINT"
                elif pd.api.types.is_float_dtype(dtype):
                    col_type = "DOUBLE"
                elif pd.api.types.is_bool_dtype(dtype):
                    col_type = "BOOLEAN"
                columns.append({"name": col, "type": col_type})
            self.table_schemas[table_name] = columns

        self._parsed = True

    def detect_tables(self) -> List[Dict[str, Any]]:
        if self._is_ocel2():
            tables = []
            try:
                event_attrs_map, object_attrs_map, events, objects, event_objects, object_objects = self._parse_xml_ocel2()
                
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
                            
                for ev_type, attrs in discovered_events.items():
                    if ev_type not in event_attrs_map:
                        event_attrs_map[ev_type] = {}
                    for a in attrs:
                        if a not in event_attrs_map[ev_type]:
                            event_attrs_map[ev_type][a] = "VARCHAR"
                            
                for obj_type, attrs in discovered_objects.items():
                    if obj_type not in object_attrs_map:
                        object_attrs_map[obj_type] = {}
                    for a in attrs:
                        if a not in object_attrs_map[obj_type]:
                            object_attrs_map[obj_type][a] = "VARCHAR"

                tables.extend([
                    {"name": "event_map_type", "columns": [{"name": "ocel_type", "type": "VARCHAR"}, {"name": "ocel_type_map", "type": "VARCHAR"}], "estimated_rows": len(event_attrs_map)},
                    {"name": "object_map_type", "columns": [{"name": "ocel_type", "type": "VARCHAR"}, {"name": "ocel_type_map", "type": "VARCHAR"}], "estimated_rows": len(object_attrs_map)},
                    {"name": "event", "columns": [{"name": "ocel_id", "type": "VARCHAR"}, {"name": "ocel_type", "type": "VARCHAR"}], "estimated_rows": len(events)},
                    {"name": "object", "columns": [{"name": "ocel_id", "type": "VARCHAR"}, {"name": "ocel_type", "type": "VARCHAR"}], "estimated_rows": len(objects)},
                    {"name": "event_object", "columns": [{"name": "ocel_event_id", "type": "VARCHAR"}, {"name": "ocel_object_id", "type": "VARCHAR"}, {"name": "ocel_qualifier", "type": "VARCHAR"}], "estimated_rows": len(event_objects)},
                    {"name": "object_object", "columns": [{"name": "ocel_source_id", "type": "VARCHAR"}, {"name": "ocel_target_id", "type": "VARCHAR"}, {"name": "ocel_qualifier", "type": "VARCHAR"}], "estimated_rows": len(object_objects)},
                ])
                
                for ev_type, attrs in event_attrs_map.items():
                    suffix = "".join(c.lower() for c in ev_type if c.isalnum())
                    cols = [{"name": "ocel_id", "type": "VARCHAR"}, {"name": "ocel_time", "type": "TIMESTAMP"}]
                    for name, t in sorted(attrs.items()):
                        cols.append({"name": name, "type": t})
                    tables.append({"name": f"event_{suffix}", "columns": cols, "estimated_rows": len([e for e in events if e.get("type") == ev_type])})
                    
                for obj_type, attrs in object_attrs_map.items():
                    suffix = "".join(c.lower() for c in obj_type if c.isalnum())
                    cols = [{"name": "ocel_id", "type": "VARCHAR"}, {"name": "ocel_time", "type": "TIMESTAMP"}, {"name": "ocel_changed_field", "type": "VARCHAR"}]
                    for name, t in sorted(attrs.items()):
                        cols.append({"name": name, "type": t})
                    row_count = sum(1 + len(o.get("attributes", []) or []) for o in objects if o.get("type") == obj_type)
                    tables.append({"name": f"object_{suffix}", "columns": cols, "estimated_rows": row_count})
                    
            except Exception as e:
                print(f"Error scanning OCEL2 XML: {e}")
            return tables
        else:
            self._parse_xml()
            tables = []
            for table_name, rows in self.tables_data.items():
                tables.append({
                    "name": table_name,
                    "columns": self.table_schemas.get(table_name, []),
                    "estimated_rows": len(rows)
                })
            return tables

    def get_preview(self, table_name: str, limit: int = 10) -> Dict[str, Any]:
        if self._is_ocel2():
            try:
                event_attrs_map, object_attrs_map, events, objects, event_objects, object_objects = self._parse_xml_ocel2()
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
            self._parse_xml()
            if table_name not in self.tables_data:
                return {"columns": [], "rows": [], "error": f"Table '{table_name}' not found."}
                
            rows = self.tables_data[table_name]
            if not rows:
                return {"columns": [], "rows": []}
                
            df = pd.DataFrame(rows[:limit])
            columns = list(df.columns)
            formatted_rows = df.where(pd.notnull(df), None).values.tolist()
            
            return {
                "columns": columns,
                "rows": formatted_rows
            }

    def convert(self, db_path: str, table_mappings: Dict[str, str]) -> List[str]:
        if self._is_ocel2():
            try:
                event_attrs_map, object_attrs_map, events, objects, event_objects, object_objects = self._parse_xml_ocel2()
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
                print(f"Error during OCEL2 XML conversion: {e}")
                return []
        else:
            self._parse_xml()
            conn_duck = duckdb.connect(db_path)
            successful_tables = []
            
            for original_name, new_name in table_mappings.items():
                if original_name not in self.tables_data:
                    continue
                try:
                    rows = self.tables_data[original_name]
                    if not rows:
                        table_exists = conn_duck.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name = '{new_name}'").fetchone()
                        if not table_exists:
                            conn_duck.execute(f'CREATE TABLE "{new_name}" (_id BIGINT);')
                        successful_tables.append(original_name)
                        continue
                    
                    df = pd.DataFrame(rows)
                    conn_duck.register('temp_df', df)
                    table_exists = conn_duck.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name = '{new_name}'").fetchone()
                    if table_exists:
                        conn_duck.execute(f'INSERT INTO "{new_name}" SELECT * FROM temp_df;')
                    else:
                        conn_duck.execute(f'CREATE TABLE "{new_name}" AS SELECT * FROM temp_df;')
                    conn_duck.unregister('temp_df')
                    successful_tables.append(original_name)
                except Exception as err:
                    print(f"Failed to copy XML table {original_name}: {err}")
                    
            conn_duck.close()
            return successful_tables
