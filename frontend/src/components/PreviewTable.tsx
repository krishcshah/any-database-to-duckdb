import React from 'react';
import { Table, ArrowRight, AlertCircle, RefreshCw } from 'lucide-react';

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

interface PreviewTableProps {
  files: UploadedFile[];
  tableMappings: Record<string, string>; // original_name -> new_name
  selectedTables: Record<string, boolean>; // original_name -> selected
  onRenameTable: (originalName: string, newName: string) => void;
  onToggleTable: (originalName: string) => void;
  activeTableKey: string | null; // "file_path::table_name"
  onSelectActiveTable: (filePath: string, tableName: string) => void;
  previewData: {
    columns: string[];
    rows: any[][];
    loading: boolean;
    error: string | null;
  };
}

export const PreviewTable: React.FC<PreviewTableProps> = ({
  files,
  tableMappings,
  selectedTables,
  onRenameTable,
  onToggleTable,
  activeTableKey,
  onSelectActiveTable,
  previewData,
}) => {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 w-full mt-6">
      {/* Sidebar: Files & Tables */}
      <div className="glass-panel rounded-2xl p-6 lg:col-span-1 flex flex-col max-h-[600px] overflow-y-auto">
        <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
          <Table className="w-5 h-5 text-indigo-400" />
          Detected Tables
        </h3>

        <div className="flex flex-col gap-4">
          {files.map((file) => {
            const hasError = !!file.error;
            return (
              <div key={file.file_path} className="border-b border-gray-800/80 pb-4 last:border-0 last:pb-0">
                <div className="flex items-center justify-between mb-2">
                  <div className="truncate pr-2">
                    <h4 className="font-semibold text-sm truncate">{file.original_filename}</h4>
                    <span className="text-xs text-indigo-400 uppercase font-mono">{file.format}</span>
                  </div>
                  <span className="text-[10px] text-gray-400 bg-gray-800 px-2 py-0.5 rounded font-mono">
                    {(file.size / 1024).toFixed(1)} KB
                  </span>
                </div>

                {hasError ? (
                  <div className="text-red-400 text-xs flex items-center gap-1 mt-1 bg-red-950/20 p-2 rounded">
                    <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                    <span>{file.error}</span>
                  </div>
                ) : file.tables.length === 0 ? (
                  <div className="text-gray-400 text-xs italic p-1">No tables detected.</div>
                ) : (
                  <div className="flex flex-col gap-2.5 mt-2">
                    {file.tables.map((table) => {
                      const mappingKey = `${file.file_path}::${table.name}`;
                      const isSelected = selectedTables[mappingKey] !== false;
                      const isActive = activeTableKey === mappingKey;
                      const userTableName = tableMappings[mappingKey] || table.name;

                      return (
                        <div
                          key={table.name}
                          onClick={() => onSelectActiveTable(file.file_path, table.name)}
                          className={`group flex flex-col p-2.5 rounded-xl transition-all cursor-pointer border ${
                            isActive
                              ? 'bg-indigo-600/20 border-indigo-500'
                              : 'bg-slate-900/40 border-gray-800 hover:border-gray-700'
                          }`}
                        >
                          <div className="flex items-center gap-2 mb-1.5" onClick={(e) => e.stopPropagation()}>
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => onToggleTable(mappingKey)}
                              className="rounded border-gray-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 w-4 h-4 cursor-pointer"
                            />
                            <div className="flex-1 min-w-0" onClick={() => onSelectActiveTable(file.file_path, table.name)}>
                              <span className="text-xs font-semibold block truncate hover:text-indigo-400">
                                {table.name}
                              </span>
                            </div>
                            <span className="text-[10px] text-gray-500 whitespace-nowrap">
                              ~{table.estimated_rows} rows
                            </span>
                          </div>

                          <div className="flex items-center gap-1 text-[11px]" onClick={(e) => e.stopPropagation()}>
                            <span className="text-gray-500">Output:</span>
                            <input
                              type="text"
                              value={userTableName}
                              disabled={!isSelected}
                              onChange={(e) => onRenameTable(mappingKey, e.target.value)}
                              className={`w-full py-0.5 px-2 text-xs rounded glass-input ${
                                !isSelected ? 'opacity-40 cursor-not-allowed' : ''
                              }`}
                              placeholder="Rename table..."
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Panel: Table Preview & Schema */}
      <div className="glass-panel rounded-2xl p-6 lg:col-span-2 flex flex-col h-[600px]">
        {activeTableKey ? (
          <div className="flex flex-col h-full">
            {/* Header Details */}
            <div className="flex items-center justify-between border-b border-gray-800 pb-4 mb-4">
              <div>
                <h3 className="font-bold text-lg text-indigo-400">
                  {activeTableKey.split('::')[1]}
                </h3>
                <p className="text-xs text-gray-400 flex items-center gap-1 mt-0.5">
                  <span>Schema & Data Preview (First 10 rows)</span>
                  <ArrowRight className="w-3 h-3 text-gray-500" />
                  <span className="text-indigo-300 font-mono">
                    {tableMappings[activeTableKey] || activeTableKey.split('::')[1]}
                  </span>
                </p>
              </div>

              {selectedTables[activeTableKey] === false && (
                <span className="text-[10px] text-yellow-400 bg-yellow-950/20 px-2.5 py-1 rounded-full font-medium border border-yellow-800/50">
                  Excluded from convert
                </span>
              )}
            </div>

            {/* Preview Grid / Schema View */}
            <div className="flex-1 min-h-0 flex flex-col">
              {previewData.loading ? (
                <div className="flex-1 flex flex-col items-center justify-center text-gray-400 gap-2">
                  <RefreshCw className="w-8 h-8 animate-spin text-indigo-500" />
                  <span>Loading table preview...</span>
                </div>
              ) : previewData.error ? (
                <div className="flex-1 flex flex-col items-center justify-center text-red-400 gap-2 p-6 bg-red-950/10 rounded-xl border border-red-900/30">
                  <AlertCircle className="w-8 h-8" />
                  <span className="text-sm font-semibold">Preview Unavailable</span>
                  <span className="text-xs text-gray-400 text-center max-w-sm">{previewData.error}</span>
                </div>
              ) : previewData.columns.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center text-gray-500 italic">
                  No preview columns available.
                </div>
              ) : (
                <div className="flex flex-col h-full">
                  {/* Schema Info Bar */}
                  <div className="mb-3">
                    <span className="text-xs text-gray-400 font-semibold mb-1.5 block">Columns & Inferred Types:</span>
                    <div className="flex flex-wrap gap-1.5 max-h-16 overflow-y-auto pb-1">
                      {/* We find active table's columns */}
                      {(() => {
                        const [fPath, tName] = activeTableKey.split('::');
                        const file = files.find(f => f.file_path === fPath);
                        const table = file?.tables.find(t => t.name === tName);
                        if (!table) return null;
                        
                        return table.columns.map((col) => (
                          <div key={col.name} className="flex items-center gap-1 bg-slate-900 border border-gray-800 text-[10px] px-2 py-0.5 rounded-full font-mono">
                            <span className="text-gray-300 font-medium">{col.name}</span>
                            <span className="text-indigo-400 text-[9px]">{col.type}</span>
                          </div>
                        ));
                      })()}
                    </div>
                  </div>

                  {/* Excel Scrollable Grid */}
                  <div className="flex-1 overflow-auto border border-gray-850 rounded-xl bg-slate-950/40">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead className="bg-slate-900/80 sticky top-0 z-10 border-b border-gray-800">
                        <tr>
                          {previewData.columns.map((col) => (
                            <th key={col} className="p-3 border-r border-gray-800/60 font-semibold text-gray-300 min-w-[120px] max-w-[220px] truncate">
                              {col}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {previewData.rows.length === 0 ? (
                          <tr>
                            <td colSpan={previewData.columns.length} className="p-8 text-center text-gray-500 italic">
                              Table contains no rows
                            </td>
                          </tr>
                        ) : (
                          previewData.rows.map((row, rIdx) => (
                            <tr key={rIdx} className="border-b border-gray-900/60 hover:bg-indigo-950/10 transition-colors">
                              {row.map((val, cIdx) => (
                                <td key={cIdx} className="p-3 border-r border-gray-900/40 text-gray-400 truncate max-w-[200px]" title={val !== null ? String(val) : 'NULL'}>
                                  {val === null ? (
                                    <span className="text-[10px] text-gray-600 italic font-mono font-bold">NULL</span>
                                  ) : typeof val === 'boolean' ? (
                                    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${val ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'}`}>
                                      {val ? 'TRUE' : 'FALSE'}
                                    </span>
                                  ) : (
                                    String(val)
                                  )}
                                </td>
                              ))}
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-500 gap-3 border border-dashed border-gray-800 rounded-xl">
            <div className="p-3 bg-gray-900/50 rounded-full">
              <Table className="w-6 h-6 text-gray-400" />
            </div>
            <p className="text-sm">Select a table on the left to inspect its schema and preview data</p>
          </div>
        )}
      </div>
    </div>
  );
};
