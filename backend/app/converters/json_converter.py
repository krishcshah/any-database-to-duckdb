import json
import pandas as pd
import duckdb
from typing import List, Dict, Any
from .base import BaseConverter

class JSONConverter(BaseConverter):
    def _load_json_data(self) -> Any:
        with open(self.file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _detect_tables_from_data(self, data: Any) -> Dict[str, List[Dict[str, Any]]]:
        """
        Groups data into table-like lists of dicts.
        Returns a dict of table_name -> list of dicts.
        """
        tables_data = {}
        if isinstance(data, list):
            # Root is a list. Check if it's empty or contains objects
            if not data:
                tables_data["data"] = []
            elif isinstance(data[0], dict):
                tables_data["data"] = data
            else:
                # List of primitives
                tables_data["data"] = [{"value": val} for val in data]
        elif isinstance(data, dict):
            # Root is a dict. Check if top level keys contain lists of objects
            has_table_keys = False
            for key, val in data.items():
                if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                    tables_data[key] = val
                    has_table_keys = True
                elif isinstance(val, list) and len(val) > 0:
                    # List of primitives under a key
                    tables_data[key] = [{"value": item} for item in val]
                    has_table_keys = True
            
            # If no lists of objects/primitives, treat the entire dictionary as a single row
            if not has_table_keys:
                tables_data["data"] = [data]
        else:
            # Primitive root
            tables_data["data"] = [{"value": data}]
            
        return tables_data

    def detect_tables(self) -> List[Dict[str, Any]]:
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
                
                # Use pd.json_normalize to flatten and get columns
                # We limit normalization to first 100 rows to estimate columns/schema quickly
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
            
            # Format rows as lists, replacing NaN with None for JSON compliance
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
                    # Create empty table
                    conn_duck.execute(f'CREATE TABLE "{new_name}" (data TEXT);')
                    successful_tables.append(original_name)
                    continue
                
                # Normalize and load to dataframe
                df = pd.json_normalize(rows, sep='_')
                
                # Convert complex columns (like lists or dicts that didn't get fully flattened) to string/JSON representations
                for col in df.columns:
                    # If column contains lists or dicts, serialize to JSON string
                    if df[col].apply(lambda x: isinstance(x, (list, dict))).any():
                        df[col] = df[col].apply(lambda x: json.dumps(x) if isinstance(x, (list, dict)) else x)
                
                conn_duck.register('temp_df', df)
                conn_duck.execute(f'CREATE TABLE "{new_name}" AS SELECT * FROM temp_df;')
                conn_duck.unregister('temp_df')
                successful_tables.append(original_name)
            except Exception as err:
                print(f"Failed to copy JSON table {original_name}: {err}")
                
        conn_duck.close()
        return successful_tables
