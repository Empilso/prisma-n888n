import React, { useMemo } from 'react';
import { motion } from 'framer-motion';

interface DataPreviewStudioProps {
    data: any[];
    completeness?: Record<string, number>;
}

const DataPreviewStudio: React.FC<DataPreviewStudioProps> = ({ data, completeness }) => {
    const columns = useMemo(() => {
        if (!data || !Array.isArray(data) || data.length === 0) return [];
        // Filtra para garantir que pegamos as chaves de um objeto válido
        const firstValidRow = data.find(row => row && typeof row === 'object');
        return firstValidRow ? Object.keys(firstValidRow) : [];
    }, [data]);

    if (!data || data.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-10 opacity-30 select-none">
                <span className="text-4xl mb-4">🧊</span>
                <span className="text-[10px] font-black uppercase tracking-[0.3em]">Nenhum dado para auditar</span>
            </div>
        );
    }

    return (
        <div className="flex flex-col gap-4">
            {/* ══ AUDIT HEALTH DASHBOARD ══ */}
            {completeness && (
                <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                    {Object.entries(completeness).map(([field, value]) => (
                        <div key={field} className="p-2 bg-white/[0.02] border border-white/[0.05] rounded-xl flex flex-col items-center gap-1 group/health">
                            <div className="text-[6px] font-black text-white/30 uppercase tracking-widest truncate w-full text-center group-hover/health:text-[var(--accent-green)] transition-all">
                                {field}
                            </div>
                            <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden mt-1 blur-[0.5px]">
                                <motion.div
                                    initial={{ width: 0 }}
                                    animate={{ width: `${value}%` }}
                                    className={`h-full ${value > 90 ? 'bg-[var(--accent-green)]' : value > 50 ? 'bg-[var(--orange)]' : 'bg-[var(--accent-red)]'}`}
                                />
                            </div>
                            <div className="text-[8px] font-mono-glass text-white/60 mt-1">{value}%</div>
                        </div>
                    ))}
                </div>
            )}

            {/* ══ PREMIUM DATA GRID ══ */}
            <div className="relative rounded-2xl border border-white/5 bg-black/40 overflow-hidden shadow-2xl">
                <div className="overflow-x-auto overflow-y-auto max-h-[400px] custom-scrollbar">
                    <table className="w-full text-left border-collapse">
                        <thead className="sticky top-0 z-20 bg-black/80 backdrop-blur-xl">
                            <tr>
                                {columns.map(col => (
                                    <th key={col} className="px-4 py-3 text-[7px] font-black text-white/30 uppercase tracking-[0.2em] border-b border-white/5 border-r border-white/[0.02]">
                                        {col}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/[0.02]">
                            {Array.isArray(data) && data.slice(0, 50).map((row, idx) => (
                                <tr key={idx} className="group/row hover:bg-white/[0.02] transition-all">
                                    {columns.map(col => (
                                        <td key={col} className="px-4 py-2.5 text-[9px] font-medium text-white/60 font-mono-glass truncate max-w-[200px] border-r border-white/[0.02] group-hover/row:text-white transition-all">
                                            {typeof row[col] === 'object' ? 'OBJ' : String(row[col])}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {Array.isArray(data) && data.length > 50 && (
                    <div className="p-3 bg-black/60 border-t border-white/5 text-center">
                        <span className="text-[7px] font-black text-white/20 uppercase tracking-[0.3em]">
                            Mostrando {Math.min(50, data.length)} de {data.length} registros • Use o Studio Completo para Auditoria Total
                        </span>
                    </div>
                )}
            </div>
        </div>
    );
};

export default DataPreviewStudio;
