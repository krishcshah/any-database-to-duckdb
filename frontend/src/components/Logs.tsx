import React, { useEffect, useRef } from 'react';
import { Terminal } from 'lucide-react';

interface LogsProps {
  logs: string[];
}

export const Logs: React.FC<LogsProps> = ({ logs }) => {
  const terminalEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  const parseLogLine = (line: string) => {
    // Look for patterns like [INFO], [SUCCESS], [WARNING], [ERROR]
    const infoRegex = /(\[INFO\]|INFO:)/i;
    const successRegex = /(\[SUCCESS\]|SUCCESS:)/i;
    const warnRegex = /(\[WARNING\]|WARNING:)/i;
    const errorRegex = /(\[ERROR\]|ERROR:)/i;

    if (errorRegex.test(line)) {
      return <span className="text-red-400">{line}</span>;
    } else if (warnRegex.test(line)) {
      return <span className="text-yellow-400">{line}</span>;
    } else if (successRegex.test(line)) {
      return <span className="text-emerald-400">{line}</span>;
    } else if (infoRegex.test(line)) {
      return <span className="text-indigo-400">{line}</span>;
    }
    return <span className="text-gray-300">{line}</span>;
  };

  return (
    <div className="glass-panel w-full rounded-2xl flex flex-col overflow-hidden shadow-2xl border border-gray-800">
      {/* Terminal Header */}
      <div className="bg-slate-950 px-5 py-3 flex items-center justify-between border-b border-gray-800/80">
        <div className="flex items-center gap-2">
          <div className="flex gap-1.5">
            <span className="w-3.5 h-3.5 rounded-full bg-rose-500/80 block"></span>
            <span className="w-3.5 h-3.5 rounded-full bg-yellow-500/80 block"></span>
            <span className="w-3.5 h-3.5 rounded-full bg-emerald-500/80 block"></span>
          </div>
          <span className="text-xs font-semibold text-gray-400 flex items-center gap-1.5 ml-4 font-mono">
            <Terminal className="w-4 h-4 text-indigo-400" />
            conversion_console.log
          </span>
        </div>
        <span className="text-[10px] text-gray-500 font-mono">UTF-8</span>
      </div>

      {/* Terminal logs body */}
      <div className="bg-slate-950/90 p-5 h-64 overflow-y-auto font-mono text-xs leading-relaxed flex flex-col gap-1.5 term-log">
        {logs.length === 0 ? (
          <span className="text-gray-500 italic">No output logs yet. Start conversion to view log details...</span>
        ) : (
          logs.map((line, idx) => (
            <div key={idx} className="flex gap-2">
              <span className="text-gray-600 select-none w-6 text-right">{(idx + 1).toString().padStart(2, '0')}</span>
              <div className="flex-1 break-all">{parseLogLine(line)}</div>
            </div>
          ))
        )}
        <div ref={terminalEndRef} />
      </div>
    </div>
  );
};
