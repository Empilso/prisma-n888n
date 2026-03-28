import React, { useEffect, useRef, useState, useCallback } from 'react';

const MIN_HEIGHT = 40;
const MAX_HEIGHT = 800;
const STORAGE_KEY = 'prisma888_terminal_height';

const AGENT_NAMES: Record<string, string> = {
    '1': 'Zorg Romário',
    '2': 'Xylos Bebeto',
    'kaka': 'Kaká Forense',
    '3': 'Dunga Alpha',
    'Sistema': 'Sistema Core'
};

const TerminalPanel = () => {
    const [logsByTab, setLogsByTab] = useState<Record<string, { msg: string, time: string }[]>>({ 'Sistema': [] });
    const [activeTab, setActiveTab] = useState('Sistema');
    const [stats, setStats] = useState({ cpu: '3.2', mem: '124', temp: '42' });

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
        const eventSource = new EventSource('http://localhost:8003/api/logs');
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.msg) {
                const match = data.msg.match(/^\[(AGENT\s+)?([^\]]+)\]/i);
                const tabId = match ? match[2].trim() : 'Sistema';
                const now = new Date();
                const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;

                setLogsByTab(prev => {
                    const currentTabLogs = prev[tabId] || [];
                    const updatedTabLogs = [...currentTabLogs, { msg: data.msg, time: timeStr }].slice(-300);
                    return { ...prev, [tabId]: updatedTabLogs };
                });
                
                // Simula oscilação de hardware
                setStats({
                    cpu: (Math.random() * 8 + 1).toFixed(1),
                    mem: (Math.random() * 50 + 100).toFixed(0),
                    temp: (Math.random() * 10 + 35).toFixed(1)
                });
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
            let newHeight = Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, startHeight + delta));
            // Magnetic snap to collapse
            if (newHeight < MIN_HEIGHT + 20) newHeight = MIN_HEIGHT;
            setHeight(newHeight);
        };

        const handleMouseUp = () => {
            setIsDragging(false);
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
            setHeight(h => {
                localStorage.setItem(STORAGE_KEY, h.toString());
                return h;
            });
        };

        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
    }, [height]);

    const toggleExpand = () => {
        const newHeight = isExpanded ? MIN_HEIGHT : 320;
        setHeight(newHeight);
        localStorage.setItem(STORAGE_KEY, newHeight.toString());
    };

    return (
        <div
            ref={panelRef}
            className="flex flex-col shrink-0 relative transition-all shadow-[0_-15px_40px_-10px_rgba(0,0,0,0.6)] z-40 border-t border-white/[0.08]"
            style={{ 
                height: `${height}px`, 
                transition: isDragging ? 'none' : 'height 0.4s cubic-bezier(0.25, 1, 0.5, 1)',
                background: 'rgba(10, 10, 14, 0.85)',
                backdropFilter: 'blur(30px) saturate(180%)',
            }}
        >
            {/* Invisível Hitbox para Drag Superior */}
            <div
                onMouseDown={handleMouseDown}
                className="absolute top-0 left-0 right-0 h-3 cursor-ns-resize z-50 hover:bg-white/[0.05] flex items-start justify-center pt-[2px]"
            >
                <div className="w-12 h-1 rounded-full bg-white/20" />
            </div>

            {/* Header / macOS Title Bar */}
            <div className={`h-10 flex items-center justify-between px-4 shrink-0 border-b ${isExpanded ? 'border-white/[0.05]' : 'border-transparent'} transition-colors relative z-40`} >
                <div className="flex items-center gap-6 h-full">
                    
                    {/* Mac window controls */}
                    <div className="flex gap-2 items-center" onClick={toggleExpand} style={{ cursor: 'pointer' }}>
                        <div className="w-3 h-3 rounded-full bg-[#ff5f56] border border-[#e0443e] hover:bg-[#ff5f56]/80 flex items-center justify-center group"><span className="opacity-0 group-hover:opacity-100 text-[#4d0000] text-[8px] font-black leading-none">✕</span></div>
                        <div className="w-3 h-3 rounded-full bg-[#ffbd2e] border border-[#dea123] hover:bg-[#ffbd2e]/80 flex items-center justify-center group"><span className="opacity-0 group-hover:opacity-100 text-[#5c3e00] text-[8px] font-black leading-none">-</span></div>
                        <div className="w-3 h-3 rounded-full bg-[#27c93f] border border-[#1aab29] hover:bg-[#27c93f]/80 flex items-center justify-center group"><span className="opacity-0 group-hover:opacity-100 text-[#004d09] text-[8px] font-black leading-none">⤢</span></div>
                    </div>

                    {/* Abas Estilo VSCode/Safari */}
                    <div className="flex items-end h-full gap-0 overflow-x-auto custom-scrollbar pt-2 pl-4 border-l border-white/[0.08]">
                        {Object.keys(logsByTab).map(tabKey => {
                            const isActive = activeTab === tabKey;
                            const isSystem = tabKey === 'Sistema';
                            return (
                                <div
                                    key={tabKey}
                                    onClick={() => setActiveTab(tabKey)}
                                    className={`px-4 py-2 rounded-t-lg text-[10px] font-medium tracking-wide cursor-pointer flex items-center gap-2 border-t border-x relative z-10 transition-all ${
                                        isActive
                                            ? 'bg-black/40 border-white/[0.08] text-white'
                                            : 'bg-transparent border-transparent text-white/40 hover:text-white/70 hover:bg-white/[0.03]'
                                    }`}
                                >
                                    <span className={isActive && !isSystem ? 'text-[var(--accent-purple)]' : ''}>
                                        {isSystem ? '~/Engine' : `agent@${tabKey}`}
                                    </span>
                                    {logsByTab[tabKey].length > 0 && (
                                        <span className={`text-[8px] font-black px-1.5 py-0.5 rounded-full ${isActive ? 'bg-white/10 text-white' : 'bg-white/[0.05] text-white/30'}`}>
                                            {logsByTab[tabKey].length}
                                        </span>
                                    )}
                                    {!isSystem && isActive && (
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
                                            className="w-4 h-4 rounded-full flex items-center justify-center hover:bg-white/10 text-[8px] opacity-60 hover:opacity-100 ml-1"
                                        >✕</button>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Status HUD Apple Pro Display */}
                <div className="flex items-center gap-4 text-[9px] font-mono tracking-widest uppercase">
                    <div className="hidden md:flex items-center gap-3 text-white/40">
                        <div className="flex items-center gap-1">
                            <span className="text-[7px]">CPU</span>
                            <span className="text-[var(--accent-purple)]">{stats.cpu}%</span>
                        </div>
                        <div className="w-px h-3 bg-white/10"></div>
                        <div className="flex items-center gap-1">
                            <span className="text-[7px]">RAM</span>
                            <span className="text-[var(--accent-blue)]">{stats.mem}MB</span>
                        </div>
                        <div className="w-px h-3 bg-white/10"></div>
                        <div className="flex items-center gap-1">
                            <span className="text-[7px]">TMP</span>
                            <span className="text-orange-400">{stats.temp}°C</span>
                        </div>
                    </div>
                    
                    <button onClick={toggleExpand} className="p-1 hover:bg-white/10 rounded-md transition-colors">
                        <svg className={`w-3.5 h-3.5 text-white/50 transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <polyline points="18 15 12 9 6 15" />
                        </svg>
                    </button>
                </div>
            </div>

            {/* Log content */}
            {isExpanded && (
                <div className="flex-1 overflow-y-auto p-4 font-mono text-[11px] bg-black/40 shadow-inner">
                    {(logsByTab[activeTab] || []).length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center opacity-30 select-none">
                            <svg className="w-12 h-12 mb-4 text-white/20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
                                <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
                                <line x1="8" y1="21" x2="16" y2="21" />
                                <line x1="12" y1="17" x2="12" y2="21" />
                            </svg>
                            <span className="text-[10px] uppercase tracking-[0.2em] font-medium font-sans">SESSÃO INATIVA NO CANAL {activeTab}</span>
                        </div>
                    ) : (
                        <div className="space-y-[2px] leading-relaxed">
                            {logsByTab[activeTab].map((logEntry, i) => {
                                const log = logEntry.msg;
                                const isError = log.includes('❌') || log.includes('ERRO');
                                const isSuccess = log.includes('✅');
                                const isStart = log.includes('🚀');
                                const isWarning = log.includes('⚠️');

                                let rowStyle = 'text-white/70 hover:bg-white/[0.02]';
                                if (isError) rowStyle = 'text-[#ff5f56] bg-[#ff5f56]/10';
                                else if (isSuccess) rowStyle = 'text-[#27c93f]';
                                else if (isStart) rowStyle = 'text-[var(--accent-purple)] bg-[var(--accent-purple)]/5 font-bold';
                                else if (isWarning) rowStyle = 'text-[#ffbd2e]';

                                return (
                                    <div key={i} className={`flex items-start gap-3 px-2 py-0.5 rounded-sm transition-colors ${rowStyle}`}>
                                        <div className="flex gap-2 shrink-0 select-none opacity-40 text-[9px] mt-0.5">
                                            <span>{logEntry.time}</span>
                                        </div>
                                        <div className="whitespace-pre-wrap break-words flex-1 font-medium">{log}</div>
                                    </div>
                                );
                            })}
                            <div ref={bottomRef} className="h-2" />
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default TerminalPanel;
