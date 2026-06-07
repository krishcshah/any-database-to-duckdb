import os
import shutil
import uuid
import time
import zipfile
from typing import List, Dict, Any, Tuple

# Use /tmp on Vercel since the filesystem is read-only elsewhere
if os.environ.get("VERCEL"):
    TEMP_DIR = "/tmp/temp_storage"
else:
    TEMP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "temp_storage"))

def init_temp_storage():
    """Ensure the base temp directory exists."""
    os.makedirs(TEMP_DIR, exist_ok=True)

def generate_session_id() -> str:
    """Generate a unique session identifier."""
    return str(uuid.uuid4())

def get_session_dir(session_id: str) -> str:
    """Get the path to a session's directory."""
    path = os.path.join(TEMP_DIR, session_id)
    os.makedirs(path, exist_ok=True)
    os.makedirs(os.path.join(path, "uploads"), exist_ok=True)
    os.makedirs(os.path.join(path, "downloads"), exist_ok=True)
    return path

def clean_old_sessions(max_age_seconds: int = 3600):
    """Delete session folders older than max_age_seconds."""
    if not os.path.exists(TEMP_DIR):
        return
    
    now = time.time()
    for item in os.listdir(TEMP_DIR):
        item_path = os.path.join(TEMP_DIR, item)
        if not os.path.isdir(item_path):
            continue
        
        try:
            # Check folder modification time
            mtime = os.path.getmtime(item_path)
            if now - mtime > max_age_seconds:
                shutil.rmtree(item_path)
                print(f"Cleaned up old session: {item}")
        except Exception as e:
            print(f"Error cleaning up session {item}: {e}")

def detect_file_format(filename: str) -> str:
    """Detect file format based on extension."""
    ext = os.path.splitext(filename.lower())[1]
    if ext in ('.sqlite', '.db', '.sqlite3'):
        return 'sqlite'
    elif ext == '.json':
        return 'json'
    elif ext == '.xml':
        return 'xml'
    elif ext == '.zip':
        return 'zip'
    return 'unknown'

def extract_zip(zip_path: str, extract_to: str) -> List[Tuple[str, str]]:
    """
    Extracts a zip file and returns a list of tuples containing (extracted_file_path, detected_format).
    """
    extracted_files = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Extract all files into the directory
            zip_ref.extractall(extract_to)
            
        # Scan extracted files
        for root, _, files in os.walk(extract_to):
            for file in files:
                # Skip system files like __MACOSX or .DS_Store
                if file.startswith('.') or '__MACOSX' in root:
                    continue
                    
                full_path = os.path.join(root, file)
                fmt = detect_file_format(file)
                if fmt in ('sqlite', 'json', 'xml'):
                    extracted_files.append((full_path, fmt))
    except Exception as e:
        print(f"Error extracting ZIP file: {e}")
        
    return extracted_files
