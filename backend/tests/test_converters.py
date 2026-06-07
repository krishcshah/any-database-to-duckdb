import os
import sqlite3
import json
import duckdb
import pytest
from app.converters.json_converter import JSONConverter
from app.converters.xml_converter import XMLConverter
from app.converters.sqlite_converter import SQLiteConverter

@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path

def test_json_converter(temp_dir):
    json_path = temp_dir / "test.json"
    data = {
        "users": [
            {"id": 1, "name": "Alice", "profile": {"age": 30}},
            {"id": 2, "name": "Bob", "profile": {"age": 25}}
        ]
    }
    with open(json_path, "w") as f:
        json.dump(data, f)
        
    converter = JSONConverter(str(json_path))
    tables = converter.detect_tables()
    assert len(tables) == 1
    assert tables[0]["name"] == "users"
    
    # Preview
    preview = converter.get_preview("users", limit=2)
    assert "name" in preview["columns"]
    assert "profile_age" in preview["columns"]
    assert len(preview["rows"]) == 2
    
    # Convert
    db_path = temp_dir / "test.duckdb"
    successful = converter.convert(str(db_path), {"users": "converted_users"})
    assert "users" in successful
    
    # Verify in DuckDB
    conn = duckdb.connect(str(db_path))
    res = conn.execute("SELECT * FROM converted_users").fetchall()
    assert len(res) == 2
    conn.close()

def test_xml_converter(temp_dir):
    xml_path = temp_dir / "test.xml"
    xml_content = """<?xml version="1.0"?>
    <company>
      <employee id="101">
        <name>John</name>
        <projects>
          <project>Alpha</project>
          <project>Beta</project>
        </projects>
      </employee>
      <employee id="102">
        <name>Jane</name>
      </employee>
    </company>
    """
    with open(xml_path, "w") as f:
        f.write(xml_content)
        
    converter = XMLConverter(str(xml_path))
    tables = converter.detect_tables()
    
    # Tables should include employee and project (since it repeats under employee)
    table_names = [t["name"] for t in tables]
    assert "employee" in table_names
    assert "project" in table_names
    
    # Convert
    db_path = temp_dir / "test.duckdb"
    successful = converter.convert(str(db_path), {"employee": "emp", "project": "proj"})
    assert "employee" in successful
    assert "project" in successful
    
    # Verify in DuckDB
    conn = duckdb.connect(str(db_path))
    employees = conn.execute("SELECT * FROM emp").fetchall()
    assert len(employees) == 2
    
    projects = conn.execute("SELECT * FROM proj").fetchall()
    assert len(projects) == 2 # Alpha and Beta
    conn.close()

def test_sqlite_converter(temp_dir):
    sqlite_path = temp_dir / "test.sqlite"
    conn_sq = sqlite3.connect(str(sqlite_path))
    conn_sq.execute("CREATE TABLE t1 (id INT, val TEXT)")
    conn_sq.execute("INSERT INTO t1 VALUES (1, 'hello'), (2, 'world')")
    conn_sq.commit()
    conn_sq.close()
    
    converter = SQLiteConverter(str(sqlite_path))
    tables = converter.detect_tables()
    assert len(tables) == 1
    assert tables[0]["name"] == "t1"
    
    # Preview
    preview = converter.get_preview("t1")
    assert preview["columns"] == ["id", "val"]
    assert len(preview["rows"]) == 2
    
    # Convert
    db_path = temp_dir / "test.duckdb"
    successful = converter.convert(str(db_path), {"t1": "t1_duck"})
    assert "t1" in successful
    
    # Verify in DuckDB
    conn = duckdb.connect(str(db_path))
    rows = conn.execute("SELECT * FROM t1_duck").fetchall()
    assert len(rows) == 2
    conn.close()
