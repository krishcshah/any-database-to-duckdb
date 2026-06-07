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

def test_json_ocel2_converter(temp_dir):
    json_path = temp_dir / "ocel.json"
    ocel_data = {
        "eventTypes": [
            {"name": "Register", "attributes": [{"name": "cost", "type": "float"}]}
        ],
        "objectTypes": [
            {"name": "Order", "attributes": [{"name": "price", "type": "float"}]}
        ],
        "events": [
            {
                "id": "e1",
                "type": "Register",
                "time": "2026-06-07T10:00:00Z",
                "attributes": [{"name": "cost", "value": 10.5}],
                "relationships": [{"objectId": "o1", "qualifier": "order"}]
            }
        ],
        "objects": [
            {
                "id": "o1",
                "type": "Order",
                "attributes": [{"name": "price", "value": 100.0, "time": "2026-06-07T10:00:00Z"}],
                "relationships": [{"objectId": "o2", "qualifier": "suborder"}]
            },
            {
                "id": "o2",
                "type": "Order",
                "attributes": []
            }
        ]
    }
    with open(json_path, "w") as f:
        json.dump(ocel_data, f)
        
    converter = JSONConverter(str(json_path))
    tables = converter.detect_tables()
    table_names = [t["name"] for t in tables]
    assert "event" in table_names
    assert "object" in table_names
    assert "event_object" in table_names
    assert "object_object" in table_names
    assert "event_register" in table_names
    assert "object_order" in table_names
    
    db_path = temp_dir / "ocel_json.duckdb"
    successful = converter.convert(str(db_path), {t: t for t in table_names})
    assert len(successful) == len(table_names)
    
    conn = duckdb.connect(str(db_path))
    events = conn.execute("SELECT * FROM event").fetchall()
    assert events == [("e1", "Register")]
    
    objects = conn.execute("SELECT ocel_id, ocel_type FROM object ORDER BY ocel_id").fetchall()
    assert objects == [("o1", "Order"), ("o2", "Order")]
    
    e2o = conn.execute("SELECT * FROM event_object").fetchall()
    assert e2o == [("e1", "o1", "order")]
    
    o2o = conn.execute("SELECT * FROM object_object").fetchall()
    assert o2o == [("o1", "o2", "suborder")]
    
    event_register = conn.execute("SELECT * FROM event_register").fetchall()
    assert len(event_register) == 1
    assert event_register[0][0] == "e1"
    assert event_register[0][2] == 10.5
    
    conn.close()

def test_xml_ocel2_converter(temp_dir):
    xml_path = temp_dir / "ocel.xml"
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <log>
      <event-types>
        <event-type name="Register">
          <attributes>
            <attribute name="cost" type="float"/>
          </attributes>
        </event-type>
      </event-types>
      <object-types>
        <object-type name="Order">
          <attributes>
            <attribute name="price" type="float"/>
          </attributes>
        </object-type>
      </object-types>
      <events>
        <event id="e1" type="Register" time="2026-06-07T10:00:00Z">
          <attributes>
            <attribute name="cost">10.5</attribute>
          </attributes>
          <objects>
            <relobj object-id="o1" qualifier="order"/>
          </objects>
        </event>
      </events>
      <objects>
        <object id="o1" type="Order">
          <attributes>
            <attribute name="price" time="2026-06-07T10:00:00Z">100.0</attribute>
          </attributes>
          <objects>
            <relobj object-id="o2" qualifier="suborder"/>
          </objects>
        </object>
        <object id="o2" type="Order">
        </object>
      </objects>
    </log>
    """
    with open(xml_path, "w") as f:
        f.write(xml_content)
        
    converter = XMLConverter(str(xml_path))
    tables = converter.detect_tables()
    table_names = [t["name"] for t in tables]
    assert "event" in table_names
    assert "object" in table_names
    assert "event_register" in table_names
    assert "object_order" in table_names
    
    db_path = temp_dir / "ocel_xml.duckdb"
    successful = converter.convert(str(db_path), {t: t for t in table_names})
    # successful includes the original table_names PLUS the flat OCEL2 schema tables
    for t in table_names:
        assert t in successful, f"Expected {t} in successful tables"
    for flat in ['events', 'objects', 'event_object', 'object_attribute_history', 'object_relations']:
        assert flat in successful, f"Expected flat table {flat} in successful tables"
    
    conn = duckdb.connect(str(db_path))
    events = conn.execute("SELECT * FROM event").fetchall()
    assert events == [("e1", "Register")]
    
    objects = conn.execute("SELECT ocel_id, ocel_type FROM object ORDER BY ocel_id").fetchall()
    assert objects == [("o1", "Order"), ("o2", "Order")]
    
    conn.close()

def test_combined_merging(temp_dir):
    xml_path = temp_dir / "ocel1.xml"
    xml_content = """<?xml version="1.0"?>
    <log>
      <events>
        <event id="e1" type="Register" time="2026-06-07T10:00:00Z"/>
      </events>
      <objects>
        <object id="o1" type="Order"/>
      </objects>
    </log>
    """
    with open(xml_path, "w") as f:
        f.write(xml_content)
        
    json_path = temp_dir / "ocel2.json"
    json_content = {
        "events": [
            {"id": "e2", "type": "Check", "time": "2026-06-07T11:00:00Z"}
        ],
        "objects": [
            {"id": "o2", "type": "Item"}
        ]
    }
    with open(json_path, "w") as f:
        json.dump(json_content, f)
        
    db_path = temp_dir / "merged.duckdb"
    
    conv_xml = XMLConverter(str(xml_path))
    res_xml = conv_xml.convert(str(db_path), {"event": "event", "object": "object"})
    assert "event" in res_xml
    
    conv_json = JSONConverter(str(json_path))
    res_json = conv_json.convert(str(db_path), {"event": "event", "object": "object"})
    assert "event" in res_json
    
    conn = duckdb.connect(str(db_path))
    events = conn.execute("SELECT ocel_id, ocel_type FROM event ORDER BY ocel_id").fetchall()
    assert events == [("e1", "Register"), ("e2", "Check")]
    
    objects = conn.execute("SELECT ocel_id, ocel_type FROM object ORDER BY ocel_id").fetchall()
    assert objects == [("o1", "Order"), ("o2", "Item")]
    conn.close()

def test_ocel2_flat_schema(temp_dir):
    # 1. Setup JSON OCEL 2.0
    json_path = temp_dir / "ocel_flat.json"
    ocel_data = {
        "eventTypes": [
            {"name": "Register", "attributes": [{"name": "cost", "type": "float"}]}
        ],
        "objectTypes": [
            {"name": "Order", "attributes": [{"name": "price", "type": "float"}]}
        ],
        "events": [
            {
                "id": "e1",
                "type": "Register",
                "time": "2026-06-07T10:00:00Z",
                "attributes": [{"name": "cost", "value": 10.5}],
                "relationships": [{"objectId": "o1", "qualifier": "order"}]
            }
        ],
        "objects": [
            {
                "id": "o1",
                "type": "Order",
                "attributes": [{"name": "price", "value": 100.0, "time": "2026-06-07T10:00:00Z"}],
                "relationships": [{"objectId": "o2", "qualifier": "suborder"}]
            },
            {
                "id": "o2",
                "type": "Order",
                "attributes": []
            }
        ]
    }
    with open(json_path, "w") as f:
        json.dump(ocel_data, f)

    conv_json = JSONConverter(str(json_path))
    db_path_json = temp_dir / "flat_json.duckdb"
    conv_json.convert(str(db_path_json), {"event": "event", "object": "object"})

    conn = duckdb.connect(str(db_path_json))
    # Check events table
    evs = conn.execute("SELECT event_id, activity, timestamp_unix, cost FROM events").fetchall()
    assert len(evs) == 1
    assert evs[0][0] == "e1"
    assert evs[0][1] == "Register"
    assert evs[0][2] == 1780826400  # Unix timestamp for 2026-06-07T10:00:00Z
    assert float(evs[0][3]) == 10.5

    # Check objects table
    objs = conn.execute("SELECT obj_id, obj_type, price FROM objects ORDER BY obj_id").fetchall()
    assert len(objs) == 2
    assert objs[0][0] == "o1"
    assert objs[0][1] == "Order"
    assert float(objs[0][2]) == 100.0
    assert objs[1][0] == "o2"
    assert objs[1][1] == "Order"
    assert objs[1][2] is None

    # Check event_object table
    e2o = conn.execute("SELECT event_id, obj_id, qualifier FROM event_object").fetchall()
    assert e2o == [("e1", "o1", "order")]

    # Check object_relations table
    o2o = conn.execute("SELECT source_obj_id, target_obj_id, qualifier FROM object_relations").fetchall()
    assert o2o == [("o1", "o2", "suborder")]

    # Check object_attribute_history table
    hist = conn.execute("SELECT obj_id, timestamp_unix, price FROM object_attribute_history").fetchall()
    assert len(hist) == 1
    assert hist[0][0] == "o1"
    assert hist[0][1] == 1780826400
    assert float(hist[0][2]) == 100.0

    conn.close()

    # 2. Setup SQLite OCEL 2.0
    sqlite_path = temp_dir / "ocel_flat.sqlite"
    conn_sq = sqlite3.connect(str(sqlite_path))
    conn_sq.execute("CREATE TABLE event (ocel_id TEXT PRIMARY KEY, ocel_type TEXT)")
    conn_sq.execute("CREATE TABLE object (ocel_id TEXT PRIMARY KEY, ocel_type TEXT)")
    conn_sq.execute("CREATE TABLE event_object (ocel_event_id TEXT, ocel_object_id TEXT, ocel_qualifier TEXT)")
    conn_sq.execute("CREATE TABLE object_object (ocel_source_id TEXT, ocel_target_id TEXT, ocel_qualifier TEXT)")
    conn_sq.execute("CREATE TABLE event_map_type (ocel_type TEXT, ocel_type_map TEXT)")
    conn_sq.execute("CREATE TABLE object_map_type (ocel_type TEXT, ocel_type_map TEXT)")
    conn_sq.execute("CREATE TABLE event_register (ocel_id TEXT PRIMARY KEY, ocel_time TEXT, cost REAL)")
    conn_sq.execute("CREATE TABLE object_order (ocel_id TEXT PRIMARY KEY, ocel_time TEXT, price REAL)")
    
    conn_sq.execute("INSERT INTO event VALUES ('e1', 'Register')")
    conn_sq.execute("INSERT INTO object VALUES ('o1', 'Order')")
    conn_sq.execute("INSERT INTO event_object VALUES ('e1', 'o1', 'order')")
    conn_sq.execute("INSERT INTO event_map_type VALUES ('Register', 'register')")
    conn_sq.execute("INSERT INTO object_map_type VALUES ('Order', 'order')")
    conn_sq.execute("INSERT INTO event_register VALUES ('e1', '2026-06-07T10:00:00Z', 10.5)")
    conn_sq.execute("INSERT INTO object_order VALUES ('o1', '2026-06-07T10:00:00Z', 100.0)")
    
    conn_sq.commit()
    conn_sq.close()

    conv_sqlite = SQLiteConverter(str(sqlite_path))
    db_path_sqlite = temp_dir / "flat_sqlite.duckdb"
    conv_sqlite.convert(str(db_path_sqlite), {"event": "event", "object": "object"})

    conn = duckdb.connect(str(db_path_sqlite))
    # Check flat tables
    evs = conn.execute("SELECT event_id, activity, timestamp_unix, cost FROM events").fetchall()
    assert len(evs) == 1
    assert evs[0][0] == "e1"
    assert evs[0][1] == "register"
    assert evs[0][2] == 1780826400
    assert float(evs[0][3]) == 10.5

    objs = conn.execute("SELECT obj_id, obj_type, price FROM objects").fetchall()
    assert len(objs) == 1
    assert objs[0][0] == "o1"
    assert objs[0][1] == "order"
    assert float(objs[0][2]) == 100.0

    conn.close()

