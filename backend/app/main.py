import os
import shutil
from typing import List, Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .utils import (
    init_temp_storage,
    generate_session_id,
    get_session_dir,
    clean_old_sessions,
    detect_file_format,
    extract_zip
)
from .converters.sqlite_converter import SQLiteConverter
from .converters.json_converter import JSONConverter
from .converters.xml_converter import XMLConverter

# Initialize FastAPI
app = FastAPI(title="DuckDB Database Converter API")

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Initialize storage directories
init_temp_storage()

# Request schemas
class PreviewRequest(BaseModel):
    session_id: str
    file_path: str
    table_name: str
    limit: int = 10

class TableMappingConfig(BaseModel):
    original_name: str
    new_name: str

class FileConvertConfig(BaseModel):
    file_path: str
    format: str
    table_mappings: Dict[str, str]  # original -> new
    original_filename: str

class ConvertRequest(BaseModel):
    session_id: str
    configs: List[FileConvertConfig]

# Logger helper
class SessionLogger:
    def __init__(self, session_dir: str):
        self.log_path = os.path.join(session_dir, "conversion.log")
        
    def log(self, message: str):
        timestamp = os.popen('date /t').read().strip() + " " + os.popen('time /t').read().strip()
        # Fallback to python time if command fails
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(log_line)
        print(log_line.strip())

    def get_logs(self) -> List[str]:
        if not os.path.exists(self.log_path):
            return []
        with open(self.log_path, "r", encoding="utf-8") as f:
            return f.readlines()

@app.post("/api/upload")
async def upload_files(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...)
):
    # Run cleanup of old files in the background
    background_tasks.add_task(clean_old_sessions)
    
    session_id = generate_session_id()
    session_dir = get_session_dir(session_id)
    uploads_dir = os.path.join(session_dir, "uploads")
    
    session_logger = SessionLogger(session_dir)
    session_logger.log(f"Initializing upload session {session_id}")
    
    response_files = []
    
    for upload_file in files:
        if not upload_file.filename:
            continue
            
        # Write file to uploads folder
        file_uuid = generate_session_id() # Unique name inside storage
        ext = os.path.splitext(upload_file.filename)[1]
        temp_filename = f"{file_uuid}{ext}"
        temp_path = os.path.join(uploads_dir, temp_filename)
        
        session_logger.log(f"Uploading file: {upload_file.filename} -> {temp_filename}")
        
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)
            
        file_size = os.path.getsize(temp_path)
        fmt = detect_file_format(upload_file.filename)
        
        # Process ZIP file or single data files
        files_to_process = []
        if fmt == 'zip':
            session_logger.log(f"Extracting zip file {upload_file.filename}")
            extract_dir = os.path.join(uploads_dir, f"{file_uuid}_extracted")
            os.makedirs(extract_dir, exist_ok=True)
            extracted = extract_zip(temp_path, extract_dir)
            session_logger.log(f"Extracted {len(extracted)} valid files from ZIP")
            for ext_path, ext_fmt in extracted:
                files_to_process.append((ext_path, ext_fmt, os.path.basename(ext_path)))
        else:
            files_to_process.append((temp_path, fmt, upload_file.filename))
            
        for path, file_format, original_name in files_to_process:
            tables = []
            error_msg = None
            
            try:
                # Detect tables
                if file_format == 'sqlite':
                    converter = SQLiteConverter(path)
                    tables = converter.detect_tables()
                elif file_format == 'json':
                    converter = JSONConverter(path)
                    tables = converter.detect_tables()
                elif file_format == 'xml':
                    converter = XMLConverter(path)
                    tables = converter.detect_tables()
                else:
                    error_msg = "Unsupported file format"
            except Exception as e:
                error_msg = f"Failed to detect schema: {str(e)}"
                session_logger.log(f"Error reading file {original_name}: {error_msg}")
                
            response_files.append({
                "original_filename": original_name,
                "file_path": path, # Backend path to the file
                "size": os.path.getsize(path),
                "format": file_format,
                "tables": tables,
                "error": error_msg
            })
            
    return {
        "session_id": session_id,
        "files": response_files
    }

@app.post("/api/preview")
async def preview_table(req: PreviewRequest):
    session_dir = get_session_dir(req.session_id)
    if not os.path.exists(req.file_path):
         raise HTTPException(status_code=404, detail="Uploaded file not found.")
         
    fmt = detect_file_format(req.file_path)
    try:
        if fmt == 'sqlite':
            converter = SQLiteConverter(req.file_path)
        elif fmt == 'json':
            converter = JSONConverter(req.file_path)
        elif fmt == 'xml':
            converter = XMLConverter(req.file_path)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format for preview.")
            
        preview_data = converter.get_preview(req.table_name, req.limit)
        return preview_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")

@app.post("/api/convert")
async def convert_database(req: ConvertRequest):
    import zipfile
    session_dir = get_session_dir(req.session_id)
    session_logger = SessionLogger(session_dir)
    session_logger.log("Starting database conversion...")
    
    downloads_dir = os.path.join(session_dir, "downloads")
    individual_dir = os.path.join(downloads_dir, "individual")
    os.makedirs(individual_dir, exist_ok=True)
    
    combined_db_path = os.path.join(downloads_dir, "combined.duckdb")
    
    # Clean build files
    if os.path.exists(combined_db_path):
        os.remove(combined_db_path)
        
    # Clean individual folder
    if os.path.exists(individual_dir):
        shutil.rmtree(individual_dir)
    os.makedirs(individual_dir, exist_ok=True)
    
    converted_tables = []
    individual_results = []
    
    for config in req.configs:
        if not os.path.exists(config.file_path):
            session_logger.log(f"Warning: File {config.file_path} not found, skipping.")
            continue
            
        base_name = os.path.basename(config.original_filename)
        name_without_ext = os.path.splitext(base_name)[0]
        indiv_db_name = f"{name_without_ext}.duckdb"
        indiv_db_path = os.path.join(individual_dir, indiv_db_name)
        
        session_logger.log(f"Converting file: {base_name} with format {config.format}")
        
        try:
            # 1. Convert to individual database
            if config.format == 'sqlite':
                converter = SQLiteConverter(config.file_path)
            elif config.format == 'json':
                converter = JSONConverter(config.file_path)
            elif config.format == 'xml':
                converter = XMLConverter(config.file_path)
            else:
                session_logger.log(f"Unsupported format: {config.format}")
                continue
            
            # Write to individual database
            indiv_success_tables = converter.convert(indiv_db_path, config.table_mappings)
            
            # 2. Write same tables to combined database
            combined_success_tables = converter.convert(combined_db_path, config.table_mappings)
            
            for orig, new in config.table_mappings.items():
                if orig in combined_success_tables:
                    session_logger.log(f"Successfully converted table: '{orig}' -> '{new}'")
                    converted_tables.append({
                        "original_name": orig,
                        "new_name": new,
                        "format": config.format
                    })
                else:
                    session_logger.log(f"Failed to convert table: '{orig}'")
                    
            if os.path.exists(indiv_db_path) and os.path.getsize(indiv_db_path) > 0:
                individual_results.append({
                    "original_filename": config.original_filename,
                    "name": indiv_db_name,
                    "size": os.path.getsize(indiv_db_path)
                })
        except Exception as e:
            session_logger.log(f"Error during conversion of {base_name}: {str(e)}")
            
    # Verify combined database
    if not os.path.exists(combined_db_path) or os.path.getsize(combined_db_path) == 0:
        session_logger.log("Error: No tables were successfully converted, database was not created.")
        raise HTTPException(status_code=400, detail="Conversion failed. No tables were written.")
        
    combined_db_size = os.path.getsize(combined_db_path)
    
    # 3. Create ZIP archive of all individual databases
    zip_path = os.path.join(downloads_dir, "individual_databases.zip")
    if os.path.exists(zip_path):
        os.remove(zip_path)
        
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file in os.listdir(individual_dir):
            file_path = os.path.join(individual_dir, file)
            zip_file.write(file_path, file)
            
    zip_size = os.path.getsize(zip_path)
    session_logger.log(f"Conversion complete! Combined DB size: {combined_db_size} bytes, ZIP size: {zip_size} bytes")
    
    # Retrieve all logs
    logs = [log.strip() for log in session_logger.get_logs()]
    
    return {
        "session_id": req.session_id,
        "combined": {
            "name": "combined.duckdb",
            "size": combined_db_size
        },
        "individual": individual_results,
        "zip": {
            "name": "individual_databases.zip",
            "size": zip_size
        },
        "converted_tables": converted_tables,
        "logs": logs
    }

@app.get("/api/download/{session_id}")
async def download_database(
    session_id: str,
    type: str = "combined",
    filename: str = None
):
    session_dir = get_session_dir(session_id)
    downloads_dir = os.path.join(session_dir, "downloads")
    
    if type == "combined":
        file_path = os.path.join(downloads_dir, "combined.duckdb")
        download_filename = "combined.duckdb"
    elif type == "zip":
        file_path = os.path.join(downloads_dir, "individual_databases.zip")
        download_filename = "individual_databases.zip"
    elif type == "individual":
        if not filename:
            raise HTTPException(status_code=400, detail="Filename parameter is required for individual download.")
        # Sanitize filename to prevent directory traversal
        clean_filename = os.path.basename(filename)
        file_path = os.path.join(downloads_dir, "individual", clean_filename)
        download_filename = clean_filename
    else:
        raise HTTPException(status_code=400, detail="Invalid download type.")
        
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Requested file not found. Please convert first.")
        
    return FileResponse(
        path=file_path,
        filename=download_filename,
        media_type="application/octet-stream"
    )
