import { useState } from 'react';
import axios from 'axios';
import { 
  Database, 
  CheckCircle, 
  XCircle, 
  Download, 
  RefreshCw, 
  Play, 
  ChevronRight,
  FileCode,
  HardDrive
} from 'lucide-react';
import { Dropzone } from './components/Dropzone';
import { PreviewTable } from './components/PreviewTable';
import { Logs } from './components/Logs';

// Type definitions
interface Column {
  name: string;
  type: string;
}

interface DetectedTable {
  name: string;
  columns: Column[];
  estimated_rows: number;
}

interface UploadedFile {
  original_filename: string;
  file_path: string;
  format: string;
  size: number;
  tables: DetectedTable[];
  error?: string | null;
}

interface ConversionResult {
  combined: {
    name: string;
    size: number;
  };
  individual: Array<{
    original_filename: string;
    name: string;
    size: number;
  }>;
  zip: {
    name: string;
    size: number;
  };
  convertedTables: Array<{
    original_name: string;
    new_name: string;
    format: string;
  }>;
}

const API_BASE = import.meta.env.DEV ? 'http://localhost:8000' : '';

function App() {
  const [step, setStep] = useState<'upload' | 'config' | 'processing' | 'success' | 'failed'>('upload');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [files, setFiles] = useState<UploadedFile[]>([]);
  
  // Table mappings: "file_path::original_name" -> "new_name"
  const [tableMappings, setTableMappings] = useState<Record<string, string>>({});
  // Selected tables: "file_path::original_name" -> boolean
  const [selectedTables, setSelectedTables] = useState<Record<string, boolean>>({});
  
  // Active table preview key
  const [activeTableKey, setActiveTableKey] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<{
    columns: string[];
    rows: any[][];
    loading: boolean;
    error: string | null;
  }>({
    columns: [],
    rows: [],
    loading: false,
    error: null,
  });

  const [logs, setLogs] = useState<string[]>([]);
  const [conversionResult, setConversionResult] = useState<ConversionResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // File Upload handler
  const handleFilesSelected = async (selectedFiles: File[]) => {
    setIsLoading(true);
    setErrorMessage(null);
    setLogs([]);
    
    const formData = new FormData();
    selectedFiles.forEach((file) => {
      formData.append('files', file);
    });

    try {
      const res = await axios.post(`${API_BASE}/api/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      const { session_id, files: processedFiles } = res.data;
      setSessionId(session_id);
      setFiles(processedFiles);

      // Initialize table mappings & selections
      const initialMappings: Record<string, string> = {};
      const initialSelected: Record<string, boolean> = {};
      let firstTableKey: string | null = null;
      let firstFilePath = '';
      let firstTableName = '';

      processedFiles.forEach((file: UploadedFile) => {
        if (!file.error && file.tables) {
          file.tables.forEach((table) => {
            const key = `${file.file_path}::${table.name}`;
            initialMappings[key] = table.name;
            initialSelected[key] = true;

            if (!firstTableKey) {
              firstTableKey = key;
              firstFilePath = file.file_path;
              firstTableName = table.name;
            }
          });
        }
      });

      setTableMappings(initialMappings);
      setSelectedTables(initialSelected);

      // Advance to config step if we have tables, else show error
      const hasTables = processedFiles.some((f: UploadedFile) => !f.error && f.tables && f.tables.length > 0);
      
      if (hasTables) {
        setStep('config');
        if (firstTableKey) {
          setActiveTableKey(firstTableKey);
          fetchPreview(session_id, firstFilePath, firstTableName);
        }
      } else {
        // Find if there is a file error or general failure
        const anyError = processedFiles.find((f: UploadedFile) => f.error)?.error || "No convertable data found in files.";
        setErrorMessage(anyError);
        setStep('failed');
      }
    } catch (err: any) {
      setErrorMessage(err.response?.data?.detail || err.message || 'Failed to upload files.');
      setStep('failed');
    } finally {
      setIsLoading(false);
    }
  };

  // Select table preview handler
  const handleSelectActiveTable = (filePath: string, tableName: string) => {
    const key = `${filePath}::${tableName}`;
    setActiveTableKey(key);
    if (sessionId) {
      fetchPreview(sessionId, filePath, tableName);
    }
  };

  // Fetch preview data
  const fetchPreview = async (sid: string, filePath: string, tableName: string) => {
    setPreviewData((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const res = await axios.post(`${API_BASE}/api/preview`, {
        session_id: sid,
        file_path: filePath,
        table_name: tableName,
        limit: 10,
      });
      setPreviewData({
        columns: res.data.columns || [],
        rows: res.data.rows || [],
        loading: false,
        error: null,
      });
    } catch (err: any) {
      setPreviewData({
        columns: [],
        rows: [],
        loading: false,
        error: err.response?.data?.detail || err.message || 'Failed to fetch table preview.',
      });
    }
  };

  // Table renaming handler (with SQL friendly cleanup)
  const handleRenameTable = (key: string, newName: string) => {
    // Replace non-alphanumeric chars with underscores, keep lowercase/uppercase, prevent double underscores
    const sanitized = newName
      .replace(/[^a-zA-Z0-9_]/g, '_')
      .replace(/_+/g, '_');
      
    setTableMappings((prev) => ({
      ...prev,
      [key]: sanitized,
    }));
  };

  // Table selection toggler
  const handleToggleTable = (key: string) => {
    setSelectedTables((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  // Perform database conversion
  const handleConvert = async () => {
    if (!sessionId) return;
    
    // Construct configuration array for selected tables
    const configs = files.map((file) => {
      const mappings: Record<string, string> = {};
      let hasSelected = false;

      file.tables.forEach((table) => {
        const key = `${file.file_path}::${table.name}`;
        const isSelected = selectedTables[key] !== false;
        
        if (isSelected) {
          mappings[table.name] = tableMappings[key] || table.name;
          hasSelected = true;
        }
      });

      if (!hasSelected) return null;

      return {
        file_path: file.file_path,
        format: file.format,
        table_mappings: mappings,
        original_filename: file.original_filename,
      };
    }).filter((c) => c !== null);

    if (configs.length === 0) {
      alert("Please select at least one table to convert.");
      return;
    }

    setStep('processing');
    setLogs(["[INFO] Handshaking with DuckDB engine...", "[INFO] Resolving output schema..."]);
    
    try {
      const res = await axios.post(`${API_BASE}/api/convert`, {
        session_id: sessionId,
        configs: configs,
      });

      const { combined, individual, zip, converted_tables, logs: apiLogs } = res.data;
      setLogs(apiLogs || ["[INFO] Database compiled successfully!"]);
      setConversionResult({
        combined,
        individual,
        zip,
        convertedTables: converted_tables,
      });
      setStep('success');
    } catch (err: any) {
      const apiLogs = err.response?.data?.logs || [];
      if (apiLogs.length > 0) {
        setLogs(apiLogs);
      } else {
        setLogs((prev) => [...prev, `[ERROR] Connection failed: ${err.message}`]);
      }
      setErrorMessage(err.response?.data?.detail || err.message || 'Conversion failed.');
      setStep('failed');
    }
  };

  // Trigger download of DuckDB file
  const handleDownload = async (
    type: 'combined' | 'zip' | 'individual',
    filename?: string,
    outputName?: string
  ) => {
    if (!sessionId) return;
    try {
      const url = `${API_BASE}/api/download/${sessionId}?type=${type}` + 
        (filename ? `&filename=${encodeURIComponent(filename)}` : '');
        
      const response = await axios({
        url: url,
        method: 'GET',
        responseType: 'blob',
      });
      const urlBlob = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = urlBlob;
      link.setAttribute('download', outputName || 'converted.duckdb');
      document.body.appendChild(link);
      link.click();
      if (link.parentNode) {
        link.parentNode.removeChild(link);
      }
      window.URL.revokeObjectURL(urlBlob);
    } catch (err: any) {
      alert('Download failed: ' + err.message);
    }
  };

  // Reset converter state
  const handleReset = () => {
    setStep('upload');
    setSessionId(null);
    setFiles([]);
    setTableMappings({});
    setSelectedTables({});
    setActiveTableKey(null);
    setPreviewData({ columns: [], rows: [], loading: false, error: null });
    setLogs([]);
    setConversionResult(null);
    setErrorMessage(null);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 flex flex-col min-h-screen">
      {/* Navbar / Top Logo */}
      <header className="flex items-center justify-between border-b border-gray-800 pb-6 mb-8">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-indigo-600/10 text-indigo-400 rounded-xl border border-indigo-500/20 shadow-lg shadow-indigo-500/5">
            <Database className="w-6 h-6 animate-glow-pulse" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-white via-gray-200 to-indigo-300 bg-clip-text text-transparent">
              DuckDB Converter
            </h1>
            <p className="text-xs text-gray-400 font-medium">Convert SQLite, JSON & XML datasets instantly</p>
          </div>
        </div>
        
        {/* Step tracker */}
        <div className="hidden md:flex items-center gap-2 text-xs font-semibold text-gray-500 font-mono">
          <span className={step === 'upload' ? 'text-indigo-400' : 'text-gray-400'}>Upload</span>
          <ChevronRight className="w-3.5 h-3.5" />
          <span className={step === 'config' ? 'text-indigo-400' : sessionId ? 'text-gray-400' : ''}>Configure & Preview</span>
          <ChevronRight className="w-3.5 h-3.5" />
          <span className={step === 'processing' ? 'text-indigo-400' : ''}>Process</span>
          <ChevronRight className="w-3.5 h-3.5" />
          <span className={step === 'success' ? 'text-indigo-400' : ''}>Download</span>
        </div>
      </header>

      {/* Main body depending on step */}
      <main className="flex-1 flex flex-col justify-center">
        {step === 'upload' && (
          <div className="max-w-3xl mx-auto w-full animate-fade-in">
            <div className="text-center mb-8">
              <h2 className="text-3xl font-extrabold mb-3 bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
                Assemble Your Local Database
              </h2>
              <p className="text-sm text-gray-400 max-w-lg mx-auto leading-relaxed">
                Upload one or multiple JSON, XML, or SQLite files. We will automatically detect types, establish schema linkages, and package them into a fast, portable DuckDB file.
              </p>
            </div>

            <Dropzone onFilesSelected={handleFilesSelected} isLoading={isLoading} />

            {isLoading && (
              <div className="mt-8 text-center text-sm text-gray-400 flex items-center justify-center gap-2">
                <RefreshCw className="w-4 h-4 animate-spin text-indigo-500" />
                <span>Reading files and analyzing schema hierarchy...</span>
              </div>
            )}
          </div>
        )}

        {step === 'config' && (
          <div className="w-full flex flex-col animate-fade-in">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-2xl font-bold">Configure Schemas & Mappings</h2>
                <p className="text-xs text-gray-400 mt-1">Check the tables you want to convert, optionally adjust their naming, and review the structural layout.</p>
              </div>

              <button
                onClick={handleConvert}
                className="flex items-center gap-2 px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold shadow-lg shadow-indigo-600/20 active:bg-indigo-700 transition-all focus:outline-none"
              >
                <Play className="w-4 h-4 fill-white" />
                Compile to DuckDB
              </button>
            </div>

            <PreviewTable
              files={files}
              tableMappings={tableMappings}
              selectedTables={selectedTables}
              onRenameTable={handleRenameTable}
              onToggleTable={handleToggleTable}
              activeTableKey={activeTableKey}
              onSelectActiveTable={handleSelectActiveTable}
              previewData={previewData}
            />

            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={handleReset}
                className="px-5 py-2.5 rounded-xl border border-gray-800 text-gray-400 hover:text-white hover:bg-gray-950 font-medium text-xs transition-all focus:outline-none"
              >
                Start Over
              </button>
            </div>
          </div>
        )}

        {step === 'processing' && (
          <div className="max-w-3xl mx-auto w-full animate-fade-in flex flex-col gap-6">
            <div className="text-center py-6">
              <RefreshCw className="w-12 h-12 animate-spin text-indigo-500 mx-auto mb-4" />
              <h2 className="text-2xl font-bold mb-2">Generating Database File</h2>
              <p className="text-xs text-gray-400">Please wait while the engines write schemas and stream rows...</p>
            </div>
            
            <Logs logs={logs} />
          </div>
        )}

        {step === 'success' && conversionResult && (
          <div className="max-w-4xl mx-auto w-full animate-fade-in">
            <div className="glass-panel rounded-2xl p-8 border border-emerald-500/20 shadow-2xl shadow-emerald-500/5 flex flex-col items-center">
              <div className="p-4 bg-emerald-500/10 text-emerald-400 rounded-full mb-6 border border-emerald-500/20">
                <CheckCircle className="w-12 h-12" />
              </div>

              <h2 className="text-3xl font-extrabold text-white mb-2 text-center">Conversion Complete!</h2>
              <p className="text-sm text-gray-400 mb-8 max-w-md text-center">
                Your data sources have been successfully compiled into DuckDB.
              </p>

              {/* Check if single or multiple files were converted */}
              {conversionResult.individual.length === 1 ? (
                /* SINGLE FILE VIEW */
                <div className="w-full max-w-2xl flex flex-col items-center">
                  {/* Database stats */}
                  <div className="grid grid-cols-2 gap-4 w-full bg-slate-950/50 border border-gray-850 p-4 rounded-xl mb-8 font-mono text-left">
                    <div className="flex flex-col gap-1 border-r border-gray-850 pr-4">
                      <span className="text-[10px] text-gray-500 uppercase flex items-center gap-1">
                        <FileCode className="w-3.5 h-3.5 text-indigo-400" /> file name
                      </span>
                      <span className="text-sm font-semibold truncate text-gray-300">
                        {(() => {
                          const indiv = conversionResult.individual[0];
                          const base = indiv.original_filename.lastIndexOf('.');
                          const baseName = base === -1 ? indiv.original_filename : indiv.original_filename.substring(0, base);
                          return `${baseName}.duckdb`;
                        })()}
                      </span>
                    </div>
                    <div className="flex flex-col gap-1 pl-4">
                      <span className="text-[10px] text-gray-500 uppercase flex items-center gap-1">
                        <HardDrive className="w-3.5 h-3.5 text-cyan-400" /> file size
                      </span>
                      <span className="text-sm font-semibold text-gray-300">
                        {(conversionResult.individual[0].size / (1024 * 1024)).toFixed(2)} MB
                      </span>
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div className="flex flex-col sm:flex-row gap-3 w-full mb-8">
                    <button
                      onClick={() => {
                        const indiv = conversionResult.individual[0];
                        const base = indiv.original_filename.lastIndexOf('.');
                        const baseName = base === -1 ? indiv.original_filename : indiv.original_filename.substring(0, base);
                        handleDownload('individual', indiv.name, `${baseName}.duckdb`);
                      }}
                      className="flex-1 flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold shadow-lg shadow-indigo-600/30 active:bg-indigo-700 transition-all focus:outline-none"
                    >
                      <Download className="w-5 h-5" />
                      Download .duckdb File
                    </button>
                    <button
                      onClick={handleReset}
                      className="px-6 py-3.5 rounded-xl border border-gray-850 hover:bg-gray-950 text-gray-300 hover:text-white font-semibold text-sm transition-all focus:outline-none"
                    >
                      Convert More Files
                    </button>
                  </div>
                </div>
              ) : (
                /* MULTIPLE FILES VIEW */
                <div className="w-full flex flex-col gap-8">
                  {/* Grid of General Downloads */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6 w-full">
                    {/* Option 1: Combined Database */}
                    <div className="bg-slate-950/40 border border-gray-850 p-6 rounded-2xl flex flex-col justify-between items-start text-left">
                      <div className="mb-6">
                        <span className="text-[10px] text-indigo-400 font-mono font-bold uppercase tracking-wider bg-indigo-500/10 px-2 py-1 rounded animate-glow-pulse">Combined DB</span>
                        <h3 className="text-lg font-bold text-white mt-3">Single Combined Database</h3>
                        <p className="text-xs text-gray-400 mt-1.5 leading-relaxed">
                          Merge all selected tables from all uploaded files into one single consolidated DuckDB database file.
                        </p>
                      </div>
                      <div className="w-full">
                        <div className="text-[11px] font-mono text-gray-500 mb-3.5 flex justify-between">
                          <span>Name: <strong className="text-gray-300">combined.duckdb</strong></span>
                          <span>Size: <strong className="text-gray-300">{(conversionResult.combined.size / (1024 * 1024)).toFixed(2)} MB</strong></span>
                        </div>
                        <button
                          onClick={() => handleDownload('combined', undefined, 'combined.duckdb')}
                          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md active:bg-indigo-700 transition-all focus:outline-none"
                        >
                          <Download className="w-4 h-4" />
                          Download Combined DB
                        </button>
                      </div>
                    </div>

                    {/* Option 2: ZIP of all individual databases */}
                    <div className="bg-slate-950/40 border border-gray-850 p-6 rounded-2xl flex flex-col justify-between items-start text-left">
                      <div className="mb-6">
                        <span className="text-[10px] text-cyan-450 font-mono font-bold uppercase tracking-wider bg-cyan-500/10 px-2 py-1 rounded">ZIP Archive</span>
                        <h3 className="text-lg font-bold text-white mt-3">All Individual DBs (ZIP)</h3>
                        <p className="text-xs text-gray-400 mt-1.5 leading-relaxed">
                          Download a single zip archive containing each file's compiled DuckDB database independently.
                        </p>
                      </div>
                      <div className="w-full">
                        <div className="text-[11px] font-mono text-gray-500 mb-3.5 flex justify-between">
                          <span>Name: <strong className="text-gray-300">individual_databases.zip</strong></span>
                          <span>Size: <strong className="text-gray-300">{(conversionResult.zip.size / (1024 * 1024)).toFixed(2)} MB</strong></span>
                        </div>
                        <button
                          onClick={() => handleDownload('zip', undefined, 'individual_databases.zip')}
                          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold shadow-md active:bg-cyan-700 transition-all focus:outline-none"
                        >
                          <Download className="w-4 h-4" />
                          Download ZIP Archive
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Option 3: List of individual databases */}
                  <div className="w-full text-left">
                    <h3 className="text-sm font-bold text-gray-300 uppercase tracking-wider mb-3 font-mono">
                      Download Individual Databases Separately
                    </h3>
                    <div className="border border-gray-900 rounded-2xl bg-slate-950/30 overflow-hidden">
                      <div className="max-h-60 overflow-y-auto p-4 flex flex-col gap-3">
                        {conversionResult.individual.map((indiv, idx) => {
                          const base = indiv.original_filename.lastIndexOf('.');
                          const baseName = base === -1 ? indiv.original_filename : indiv.original_filename.substring(0, base);
                          const targetName = `${baseName}.duckdb`;
                          
                          return (
                            <div key={idx} className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-3 rounded-xl bg-slate-900/60 border border-gray-850 hover:border-gray-800 transition-colors">
                              <div className="truncate flex-1 min-w-0">
                                <span className="text-xs font-semibold text-gray-200 block truncate">{indiv.original_filename}</span>
                                <span className="text-[10px] text-gray-500 font-mono mt-0.5 block">
                                  Output file: <span className="text-indigo-400">{targetName}</span> • {(indiv.size / 1024).toFixed(1)} KB
                                </span>
                              </div>
                              <button
                                onClick={() => handleDownload('individual', indiv.name, targetName)}
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-800 hover:border-gray-700 hover:bg-slate-950 text-indigo-400 hover:text-indigo-300 text-xs font-semibold transition-all focus:outline-none whitespace-nowrap self-stretch sm:self-auto justify-center"
                              >
                                <Download className="w-3.5 h-3.5" />
                                Download DB
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                  {/* Global Reset buttons */}
                  <div className="flex justify-center w-full">
                    <button
                      onClick={handleReset}
                      className="px-8 py-3 rounded-xl border border-gray-850 hover:bg-gray-950 text-gray-300 hover:text-white font-semibold text-sm transition-all focus:outline-none"
                    >
                      Convert More Files
                    </button>
                  </div>
                </div>
              )}

              {/* Converted Tables Summary */}
              <div className="w-full text-left mt-8 pt-6 border-t border-gray-900">
                <h4 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3 font-mono">
                  Compiled Tables ({conversionResult.convertedTables.length})
                </h4>
                <div className="max-h-40 overflow-y-auto border border-gray-900 rounded-xl bg-slate-950/30 p-2 flex flex-col gap-1.5">
                  {conversionResult.convertedTables.map((t, idx) => (
                    <div key={idx} className="flex items-center justify-between text-xs py-1.5 px-3 rounded bg-slate-900/60 border border-gray-900">
                      <div className="truncate flex items-center gap-2">
                        <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full"></span>
                        <span className="text-gray-400 text-[10px] uppercase font-mono">{t.format}</span>
                        <span className="text-gray-500">/</span>
                        <span className="font-semibold text-gray-300 truncate">{t.original_name}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] text-gray-500">→</span>
                        <span className="font-mono text-indigo-400 font-semibold">{t.new_name}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {step === 'failed' && (
          <div className="max-w-2xl mx-auto w-full animate-fade-in">
            <div className="glass-panel rounded-2xl p-8 border border-rose-500/20 shadow-2xl shadow-rose-500/5 flex flex-col items-center text-center">
              <div className="p-4 bg-rose-500/10 text-rose-400 rounded-full mb-6 border border-rose-500/20">
                <XCircle className="w-12 h-12" />
              </div>

              <h2 className="text-3xl font-extrabold text-white mb-2">Conversion Failed</h2>
              <p className="text-sm text-gray-400 mb-6">
                An error occurred while compiling your data into a DuckDB file.
              </p>

              <div className="w-full bg-slate-950/70 border border-gray-900 rounded-xl p-4 mb-8 text-left text-xs font-mono text-red-400 break-all max-h-48 overflow-y-auto">
                {errorMessage || "Unknown server error."}
              </div>

              {logs.length > 0 && (
                <div className="w-full text-left mb-6">
                  <h4 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2 font-mono">Console Logs</h4>
                  <Logs logs={logs} />
                </div>
              )}

              <div className="flex gap-3 w-full">
                <button
                  onClick={handleReset}
                  className="flex-1 px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition-all focus:outline-none"
                >
                  Try Again
                </button>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="mt-12 border-t border-gray-900 pt-6 text-center text-xs text-gray-500 flex flex-col sm:flex-row items-center justify-between gap-4">
        <span>DuckDB Database Converter &copy; 2026. Production-Ready.</span>
        <div className="flex gap-4">
          <span className="hover:text-gray-400 cursor-pointer">Privacy Policy</span>
          <span className="hover:text-gray-400 cursor-pointer">Terms of Service</span>
        </div>
      </footer>
    </div>
  );
}

export default App;
