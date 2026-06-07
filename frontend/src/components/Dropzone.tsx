import React, { useState, useRef } from 'react';
import { Upload, FileCode, Archive } from 'lucide-react';

interface DropzoneProps {
  onFilesSelected: (files: File[]) => void;
  isLoading: boolean;
}

export const Dropzone: React.FC<DropzoneProps> = ({ onFilesSelected, isLoading }) => {
  const [isDragActive, setIsDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setIsDragActive(true);
    } else if (e.type === "dragleave") {
      setIsDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0 && !isLoading) {
      const filesArray = Array.from(e.dataTransfer.files);
      onFilesSelected(filesArray);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files.length > 0 && !isLoading) {
      const filesArray = Array.from(e.target.files);
      onFilesSelected(filesArray);
    }
  };

  const onButtonClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  return (
    <div
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDragLeave={handleDrag}
      onDrop={handleDrop}
      className={`glass-panel w-full p-12 rounded-2xl flex flex-col items-center justify-center border-2 border-dashed transition-all duration-300 ${
        isDragActive 
          ? 'border-indigo-500 bg-indigo-950/20 scale-[1.01]' 
          : 'border-gray-700 hover:border-gray-500 bg-gray-900/30'
      } ${isLoading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
      onClick={onButtonClick}
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".json,.xml,.sqlite,.db,.sqlite3,.zip"
        className="hidden"
        disabled={isLoading}
        onChange={handleChange}
      />
      
      <div className={`p-4 rounded-full mb-4 transition-transform ${isDragActive ? 'scale-110 bg-indigo-500/20 text-indigo-400' : 'bg-gray-800 text-gray-400'}`}>
        <Upload className="w-8 h-8" />
      </div>

      <h3 className="text-xl font-semibold mb-2">Drag & drop files here</h3>
      <p className="text-sm text-gray-400 mb-6 text-center max-w-md">
        Supported formats: <span className="text-indigo-400 font-medium">JSON (.json)</span>, <span className="text-indigo-400 font-medium">XML (.xml)</span>, <span className="text-indigo-400 font-medium">SQLite (.sqlite, .db, .sqlite3)</span> or <span className="text-indigo-400 font-medium">ZIP</span> containing these files.
      </p>

      <button
        type="button"
        disabled={isLoading}
        className="px-6 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 text-white font-medium shadow-lg hover:shadow-indigo-500/20 transition-all focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
      >
        Browse Files
      </button>

      <div className="mt-8 flex gap-6 text-xs text-gray-500">
        <span className="flex items-center gap-1.5">
          <FileCode className="w-4 h-4 text-cyan-400" /> Auto schema inference
        </span>
        <span className="flex items-center gap-1.5">
          <Archive className="w-4 h-4 text-emerald-400" /> Multi-file ZIP support
        </span>
      </div>
    </div>
  );
};
