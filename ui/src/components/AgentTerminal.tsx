import React, { useEffect, useRef, useState } from 'react';

const AgentTerminal = ({ agentId }: { agentId: string }) => {
    const [logs, setLogs] = useState<string[]>([]);
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        setLogs([]); // limpa ao trocar de agente
        
        // Carrega histórico gravado em disco
        fetch(`http://localhost:8003/api/agent-logs/${agentId}`)
            .then(res => res.json())
            .then(data => {
                if (data.logs && data.logs.length > 0) {
                    setLogs(data.logs);
                }
            })
            .catch(() => {});

        const eventSource = new EventSource('http://localhost:8003/api/logs');
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.msg) {
                // Filtra para mostrar APENAS se tiver a tag do agente ou for do motor (ex: Agent 2 = [2])
                const regex = new RegExp(`^\\[(AGENT\\s+)?${agentId}\\]`, 'i');
                if (regex.test(data.msg) || agentId === 'all') {
                    setLogs(prev => [...prev.slice(-150), data.msg]);
                }
            }
        };
        return () => eventSource.close();
    }, [agentId]);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [logs]);

    return (
        <div className="flex-1 bg-[#050505] rounded-xl border border-white/5 shadow-inner mt-2 min-h-[300px] max-h-[500px] overflow-hidden flex flex-col">
            <div className="h-8 border-b border-white/[0.04] bg-white/[0.01] flex items-center px-4 justify-between">
                <div className="flex items-center gap-2">
                    <span className="text-[10px]">🖥️</span>
                    <span className="text-[9px] font-black uppercase text-white/50 tracking-widest">Console Dedicado • Agente {agentId?.replace('zidane_', '')}</span>
                </div>
                {logs.length > 0 && <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent-purple)] animate-pulse shadow-[0_0_8px_var(--accent-purple)]" />}
            </div>

            <div className="flex-1 overflow-y-auto p-4 font-mono-glass text-[10px] text-[var(--text-secondary)] leading-relaxed custom-scrollbar">
                {logs.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center opacity-30">
                        <span className="text-2xl mb-2">📡</span>
                        <span className="text-[8px] font-black tracking-widest text-[var(--text-secondary)] uppercase">Aguardando sinais...</span>
                    </div>
                ) : (
                    <div className="space-y-1.5">
                        {logs.map((log, i) => {
                            const isError = log.includes('❌') || log.includes('ERRO');
                            const isSuccess = log.includes('✅');
                            const isStart = log.includes('🚀');

                            return (
                                <div key={i} className={`py-1 px-2 rounded flex gap-2 ${isError ? 'bg-red-500/10 text-red-400 border border-red-500/20' : isSuccess ? 'bg-green-500/5 text-green-400' : isStart ? 'bg-[var(--accent-purple)]/10 text-white' : 'hover:bg-white/[0.02]'}`}>
                                    <span className="text-white/20 select-none shrink-0 text-right font-black w-6">{(i + 1).toString().padStart(3, '0')}</span>
                                    <span className="whitespace-pre-wrap">{log}</span>
                                </div>
                            );
                        })}
                        <div ref={bottomRef} className="h-4" />
                    </div>
                )}
            </div>
        </div>
    );
};

export default AgentTerminal;
