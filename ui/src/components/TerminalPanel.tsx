import React, { useEffect, useRef, useState, useCallback } from 'react';

const MIN_HEIGHT = 36;
const MAX_HEIGHT = 600;
const STORAGE_KEY = 'prisma888_terminal_height';

const AGENT_NAMES: Record<string, string> = {
    '1': 'Zorg Romário',
    '2': 'Xylos Bebeto',
    'kaka': 'Kaká Forense',
    '3': 'Dunga Alpha',
    'Sistema': 'Sistema'
};

const TerminalPanel = () => {
    // Agora os logs são separados por abas (Agent IDs)
    const [logsByTab, setLogsByTab] = useState<Record<string, string[]>>({ 'Sistema': [] });
    const [activeTab, setActiveTab] = useState('Sistema');

    const [height, setHeight] = useState(() => {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            return saved ? parseInt(saved) : MIN_HEIGHT;
        } catch {
            return MIN_HEIGHT;
        }
    });
    const [isDragging, setIsDragging] = useState(false);
    const bottomRef = useRef<HTMLDivElement>(null);
    const panelRef = useRef<HTMLDivElement>(null);

    const isExpanded = height > MIN_HEIGHT + 10;

    // SSE log connection
    useEffect(() => {
        const eventSource = new EventSource('http://localhost:8001/api/logs');
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.msg) {
                // Tenta parear [agent_id] ou [AGENT agent_id]
                const match = data.msg.match(/^\[(AGENT\s+)?([^\]]+)\]/i);
                const tabId = match ? match[2].trim() : 'Sistema';

                setLogsByTab(prev => {
                    const currentTabLogs = prev[tabId] || [];
                    const updatedTabLogs = [...currentTabLogs, data.msg].slice(-300);
                    const newState = { ...prev, [tabId]: updatedTabLogs };
                    return newState;
                });

                // Opcional: auto-focus na nova aba se ela for criada agora (e não for mix)
                // if (!logsByTab[tabId]) setActiveTab(tabId);
            }
        };
        return () => eventSource.close();
    }, []);

    // Auto-scroll
    useEffect(() => {
        if (isExpanded) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [logsByTab, activeTab, isExpanded]);

    // Drag resize handler
    const handleMouseDown = useCallback((e: React.MouseEvent) => {
        e.preventDefault();
        setIsDragging(true);
        const startY = e.clientY;
        const startHeight = height;

        const handleMouseMove = (me: MouseEvent) => {
            const delta = startY - me.clientY;
            const newHeight = Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, startHeight + delta));
            setHeight(newHeight);
        };

        const handleMouseUp = () => {
            setIsDragging(false);
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
            // Save height
            setHeight(h => {
                localStorage.setItem(STORAGE_KEY, h.toString());
                return h;
            });
        };

        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
    }, [height]);

    // Toggle expand/collapse on click
    const toggleExpand = () => {
        const newHeight = isExpanded ? MIN_HEIGHT : 280;
        setHeight(newHeight);
        localStorage.setItem(STORAGE_KEY, newHeight.toString());
    };

    return (
        <div
            ref={panelRef}
            className="border-t border-white/[0.04] flex flex-col shrink-0 bg-[rgba(8,8,12,0.95)] relative"
            style={{ height: `${height}px`, transition: isDragging ? 'none' : 'height 0.4s cubic-bezier(0.16, 1, 0.3, 1)' }}
        >
            {/* Drag handle (top edge) */}
            <div
                onMouseDown={handleMouseDown}
                className={`absolute top-0 left-0 right-0 h-2 cursor-ns-resize z-10 flex items-center justify-center group hover:bg-white/[0.03] ${isDragging ? 'bg-[var(--accent-purple)]/10' : ''}`}
            >
                <div className={`w-8 h-0.5 rounded-full transition-colors ${isDragging ? 'bg-[var(--accent-purple)]' : 'bg-white/10 group-hover:bg-white/20'}`} />
            </div>

            {/* Header bar com Abas */}
            <div className="h-9 flex items-center justify-between px-5 bg-black/40 shrink-0 border-b border-white/[0.02]">
                <div className="flex items-center gap-3 h-full">
                    <div className="flex gap-1.5 mr-3" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
                        <div className="w-[8px] h-[8px] rounded-full bg-[var(--accent-red)] shadow-[0_0_8px_rgba(255,59,48,0.5)]" />
                        <div className="w-[8px] h-[8px] rounded-full bg-[var(--accent-yellow)] shadow-[0_0_8px_rgba(255,204,0,0.5)]" />
                        <div className="w-[8px] h-[8px] rounded-full bg-[var(--accent-green)] shadow-[0_0_8px_rgba(52,199,89,0.5)]" />
                    </div>

                    {/* Renderização das Abas Dinâmicas */}
                    <div className="flex items-end h-full gap-1 overflow-x-auto custom-scrollbar pt-2">
                        {Object.keys(logsByTab).map(tabKey => (
                            <div
                                key={tabKey}
                                onClick={() => setActiveTab(tabKey)}
                                className={`px-4 py-1.5 rounded-t-lg text-[10px] font-black tracking-widest uppercase cursor-pointer transition-all border-t border-x flex items-center gap-3 ${activeTab === tabKey
                                    ? 'bg-[rgba(8,8,12,0.95)] border-white/10 text-white shadow-[0_-5px_15px_rgba(0,0,0,0.5)] z-10'
                                    : 'bg-white/[0.02] border-transparent text-white/30 hover:text-white/60 hover:bg-white/[0.04]'}`}
                            >
                                <div className="flex items-center gap-2">
                                    <span className={activeTab === tabKey ? 'text-[var(--accent-purple)]' : ''}>
                                        TERMINAL {AGENT_NAMES[tabKey] ? AGENT_NAMES[tabKey].toUpperCase() : tabKey.toUpperCase()}
                                    </span>
                                    <span className="text-[7px] bg-white/10 px-1.5 py-0.5 rounded-full">{logsByTab[tabKey].length}</span>
                                </div>
                                {tabKey !== 'Sistema' && (
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setLogsByTab(prev => {
                                                const newLogs = { ...prev };
                                                delete newLogs[tabKey];
                                                return newLogs;
                                            });
                                            if (activeTab === tabKey) setActiveTab('Sistema');
                                        }}
                                        className="text-[10px] opacity-40 hover:opacity-100 hover:text-red-400 transition-colors ml-1"
                                        title="Fechar Aba"
                                    >
                                        ✕
                                    </button>
                                )}
                            </div>
                        ))}
                    </div>
                </div>

                <div className="flex items-center gap-4 py-2 cursor-pointer" onClick={toggleExpand}>
                    <span className="text-[9px] text-[var(--accent-purple)] font-black animate-pulse tracking-widest bg-[var(--accent-purple)]/10 px-2 py-1 rounded border border-[var(--accent-purple)]/20 shadow-[0_0_10px_rgba(191,90,242,0.2)]">MULTIPLEXER ATIVO</span>
                    <svg
                        className={`w-3.5 h-3.5 text-[var(--text-tertiary)] transition-transform duration-400 ${isExpanded ? 'rotate-180' : ''}`}
                        viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <polyline points="18 15 12 9 6 15" />
                    </svg>
                </div>
            </div>

            {/* Log content */}
            {isExpanded && (
                <div className="flex-1 overflow-y-auto px-5 pb-3 font-mono-glass pt-3 bg-[rgba(8,8,12,0.95)]">
                    {(logsByTab[activeTab] || []).length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center opacity-30">
                            <span className="text-4xl mb-4">🖥️</span>
                            <span className="text-[10px] font-black tracking-widest text-[var(--text-secondary)]">AGUARDANDO SINAIS NO CANAL {activeTab.toUpperCase()}</span>
                        </div>
                    ) : (
                        <div className="text-[11px] text-[var(--text-secondary)] leading-relaxed space-y-1">
                            {logsByTab[activeTab].map((log, i) => {
                                // Realce para operações importantes
                                const isError = log.includes('❌') || log.includes('ERRO');
                                const isSuccess = log.includes('✅');
                                const isStart = log.includes('🚀');

                                return (
                                    <div key={i} className={`py-1 px-2 rounded flex gap-3 ${isError ? 'bg-red-500/10 text-red-400 border border-red-500/20' : isSuccess ? 'bg-green-500/5 text-green-400' : isStart ? 'bg-[var(--accent-purple)]/10 text-white' : 'hover:bg-white/[0.02]'}`}>
                                        <span className="text-white/20 select-none shrink-0 w-8 text-right font-black">{(i + 1).toString().padStart(4, '0')}</span>
                                        <span className="whitespace-pre-wrap">{log}</span>
                                    </div>
                                );
                            })}
                            <div ref={bottomRef} className="h-4" />
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default TerminalPanel;
