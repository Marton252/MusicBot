import { useEffect, useMemo, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { ListFilter, Trash2 } from 'lucide-react';
import type { Copy } from '../i18n';

type Level = 'ALL' | 'INFO' | 'WARNING' | 'ERROR';

function LogLine({ text }: { text: string }) {
  const levelMatch = text.match(/\[(INFO|ERROR|WARNING)]/);
  const color = levelMatch?.[1] === 'ERROR' ? 'text-red-300' : levelMatch?.[1] === 'WARNING' ? 'text-yellow-300' : 'text-sky-300';
  const parts = levelMatch ? [text.slice(0, levelMatch.index), levelMatch[0], text.slice((levelMatch.index ?? 0) + levelMatch[0].length)] : [text];

  if (!levelMatch) return <>{text}</>;
  return (
    <>
      {parts[0]}
      <span className={color}>{parts[1]}</span>
      {parts[2]}
    </>
  );
}

export function LogPanel({ logs, t }: { logs: string[]; t: Copy }) {
  const reduceMotion = useReducedMotion();
  const [level, setLevel] = useState<Level>('ALL');
  const [localClearIndex, setLocalClearIndex] = useState(0);
  const [follow, setFollow] = useState(true);
  const endRef = useRef<HTMLDivElement>(null);
  const visibleLogs = useMemo(() => {
    const scoped = logs.slice(localClearIndex);
    return level === 'ALL' ? scoped : scoped.filter((line) => line.includes(`[${level}]`));
  }, [level, localClearIndex, logs]);

  useEffect(() => {
    if (follow) endRef.current?.scrollIntoView({ block: 'end' });
  }, [follow, visibleLogs.length]);

  return (
    <motion.section
      className="rounded-lg border border-panel bg-black shadow-panel"
      initial={reduceMotion ? false : { opacity: 0, y: 10 }}
      animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
    >
      <div className="flex flex-col gap-3 border-b border-panel px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-ok" />
          <h2 className="font-mono text-sm font-semibold text-white">{t.logs}</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <div className="inline-flex items-center gap-1 rounded-md border border-panel bg-app p-1 text-xs">
            <ListFilter className="h-4 w-4 text-muted" />
            {(['ALL', 'INFO', 'WARNING', 'ERROR'] as const).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setLevel(item)}
                className={`rounded px-2 py-1 font-semibold ${level === item ? 'bg-accent text-white' : 'text-muted hover:bg-panel hover:text-white'}`}
              >
                {item === 'ALL' ? t.allLevels : item}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setFollow((v) => !v)}
            className={`rounded-md border border-panel px-3 py-1.5 text-xs font-semibold ${follow ? 'bg-panel text-white' : 'text-muted hover:bg-panel hover:text-white'}`}
          >
            {t.followLogs}
          </button>
          <button
            type="button"
            onClick={() => setLocalClearIndex(logs.length)}
            className="inline-flex items-center gap-1 rounded-md border border-panel px-3 py-1.5 text-xs font-semibold text-muted hover:bg-panel hover:text-white"
          >
            <Trash2 className="h-3.5 w-3.5" />
            {t.clearLogs}
          </button>
        </div>
      </div>
      <div className="h-80 overflow-y-auto p-4 font-mono text-xs leading-6 text-slate-200 sm:h-96">
        {visibleLogs.length === 0 && <div className="text-muted">{t.noLogs}</div>}
        {visibleLogs.map((log, index) => (
          <motion.div
            key={`${index}-${log}`}
            className="break-words"
            initial={reduceMotion ? false : { opacity: 0, y: 3 }}
            animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
            transition={{ duration: 0.14 }}
          >
            <LogLine text={log} />
          </motion.div>
        ))}
        <div ref={endRef} />
      </div>
    </motion.section>
  );
}
