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

        # 1. First pass: Assign IDs and identify paths & counts
        element_ids = {}
        path_counts = {}
        table_paths: Set[Tuple[str, ...]] = set()
        
        id_counter = 0
        
        def analyze_node(node: ET.Element, path: Tuple[str, ...]):
            nonlocal id_counter
            id_counter += 1
            element_ids[node] = id_counter
            
            path_counts[path] = path_counts.get(path, 0) + 1
            
            # Count child tags under this node to detect repeating sibling tags (arrays)
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
        
        # Direct children of the root are always table paths
        for child in root:
            table_paths.add((root.tag, child.tag))
            
        analyze_node(root, root_path)

        # 2. Map paths to unique table names
        path_to_tablename = {}
        used_names = set()
        for path in table_paths:
            # Default name is the tag name
            name = path[-1]
            if name in used_names:
                # Resolve collision using full path
                name = "_".join(path[1:])
            used_names.add(name)
            path_to_tablename[path] = name

        # 3. Second pass: Extract data rows
        self.tables_data = {name: [] for name in path_to_tablename.values()}

        def extract_text(node: ET.Element) -> str:
            # Recursively extract text from non-table elements
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
                
                # Extract attributes
                for attr_name, attr_val in node.attrib.items():
                    row[attr_name] = attr_val
                
                # If this table node itself has text and no children, store it in "value"
                if node.text and node.text.strip() and len(node) == 0:
                    row["value"] = node.text.strip()
                
                # Extract simple children (non-table children)
                for child in node:
                    child_path = path + (child.tag,)
                    if child_path not in table_paths:
                        child_text = extract_text(child)
                        if child_text:
                            # Handle duplicate child tag text by joining them
                            if child.tag in row:
                                row[child.tag] = f"{row[child.tag]}; {child_text}"
                            else:
                                row[child.tag] = child_text
                
                self.tables_data[table_name].append(row)
                current_table_id = node_id
                current_table_tag = table_name

            # Recurse to children
            for child in node:
                child_path = path + (child.tag,)
                extract_data(child, child_path, current_table_id, current_table_tag)

        extract_data(root, root_path, None, "")

        # 4. Generate schemas for each table
        self.table_schemas = {}
        for table_name, rows in self.tables_data.items():
            if not rows:
                self.table_schemas[table_name] = []
                continue
            
            # Use pandas to infer types from all extracted rows
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
        self._parse_xml()
        conn_duck = duckdb.connect(db_path)
        successful_tables = []
        
        for original_name, new_name in table_mappings.items():
            if original_name not in self.tables_data:
                continue
            try:
                rows = self.tables_data[original_name]
                if not rows:
                    # Create empty table
                    conn_duck.execute(f'CREATE TABLE "{new_name}" (_id BIGINT);')
                    successful_tables.append(original_name)
                    continue
                
                df = pd.DataFrame(rows)
                conn_duck.register('temp_df', df)
                conn_duck.execute(f'CREATE TABLE "{new_name}" AS SELECT * FROM temp_df;')
                conn_duck.unregister('temp_df')
                successful_tables.append(original_name)
            except Exception as err:
                print(f"Failed to copy XML table {original_name}: {err}")
                
        conn_duck.close()
        return successful_tables
