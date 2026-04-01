import React, { useState } from 'react';
import { Upload, Download, FileText, CheckCircle2 } from 'lucide-react';

interface PeleUploadPanelProps {
    selectedAno: number | 'all';
    tipoFixo?: 'parlamentares' | 'transferencias';
}

const PeleUploadPanel: React.FC<PeleUploadPanelProps> = ({ selectedAno, tipoFixo }) => {
    const [uploadMode, setUploadMode] = useState<'manual' | 'auto'>('manual');
    const [tipoEmenda, setTipoEmenda] = useState(tipoFixo || 'parlamentares');
    const [uploadedFiles, setUploadedFiles] = useState<string[]>([]);
    const [uploading, setUploading] = useState(false);
    const [uploadStatus, setUploadStatus] = useState('');

    const tiposInfo = {
        parlamentares: {
            nome: "Emendas Parlamentares (Estaduais BA)",
            arquivos: 5,
            descricao: "Deputados estaduais — orçamento BA",
            agente: "Pelé-A1"
        },
        transferencias: {
            nome: "Transferências Especiais (Emendas Pix)",
            arquivos: 5,
            descricao: "Emendas federais repassadas ao estado",
            agente: "Pelé-A2"
        }
    };

    const tipoAtual = tipoFixo || tipoEmenda;

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (!files || files.length === 0) return;

        setUploading(true);
        setUploadStatus('Enviando arquivos...');

        try {
            const uploaded: string[] = [];
            for (let i = 0; i < files.length; i++) {
                const formData = new FormData();
                formData.append('file', files[i]);
                formData.append('ano', selectedAno.toString());
                formData.append('tipo', tipoEmenda);

                const res = await fetch('http://localhost:8003/api/pele/upload-csv', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    uploaded.push(data.filename);
                }
            }
            setUploadedFiles(prev => [...prev, ...uploaded]);
            setUploadStatus(`✓ ${uploaded.length} arquivo(s) carregado(s)`);
        } catch (e) {
            setUploadStatus('✗ Erro no upload');
        } finally {
            setUploading(false);
        }
    };

    return (
        <div className="px-4 py-3 border-t border-white/[0.05]">
            <div className="text-[11px] font-black text-white/30 uppercase tracking-[0.15em] mb-3 flex items-center gap-2">
                <FileText size={11} />
                📂 Fonte de Dados
            </div>

            {/* Tabs: Upload Manual vs Download Auto */}
            <div className="flex gap-2 mb-3">
                <button
                    onClick={() => setUploadMode('manual')}
                    className={`flex-1 px-3 py-2 rounded-lg text-[10px] font-bold uppercase tracking-wide transition-all ${
                        uploadMode === 'manual'
                            ? 'bg-blue-500/20 text-blue-300 border border-blue-400/30'
                            : 'bg-white/[0.03] text-white/40 border border-white/[0.06] hover:bg-white/[0.06]'
                    }`}
                >
                    <Upload size={12} className="inline mr-1" />
                    Upload Manual
                </button>
                <button
                    onClick={() => setUploadMode('auto')}
                    className={`flex-1 px-3 py-2 rounded-lg text-[10px] font-bold uppercase tracking-wide transition-all ${
                        uploadMode === 'auto'
                            ? 'bg-purple-500/20 text-purple-300 border border-purple-400/30'
                            : 'bg-white/[0.03] text-white/40 border border-white/[0.06] hover:bg-white/[0.06]'
                    }`}
                >
                    <Download size={12} className="inline mr-1" />
                    Download Auto
                </button>
            </div>

            {/* Upload Manual */}
            {uploadMode === 'manual' && (
                <div className="space-y-3">
                    {!tipoFixo && (
                        <select
                            value={tipoEmenda}
                            onChange={(e) => {
                                setTipoEmenda(e.target.value);
                                setUploadedFiles([]);
                                setUploadStatus('');
                            }}
                            className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white/70 text-[11px] focus:outline-none focus:border-blue-400/30"
                        >
                            <option value="parlamentares">📋 Emendas Parlamentares (Estaduais BA)</option>
                            <option value="transferencias">💰 Transferências Especiais (Pix/Federais)</option>
                        </select>
                    )}

                    {/* Info Box */}
                    <div className="p-3 rounded-lg bg-blue-500/5 border border-blue-400/20 space-y-2">
                        <div className="text-[10px] font-bold text-blue-300 uppercase tracking-wide">
                            {tiposInfo[tipoAtual as keyof typeof tiposInfo].agente}: {tiposInfo[tipoAtual as keyof typeof tiposInfo].nome}
                        </div>
                        <div className="text-[9px] text-blue-300/70">
                            {tiposInfo[tipoAtual as keyof typeof tiposInfo].descricao}
                        </div>
                        <div className="flex items-center gap-2 text-[9px] text-amber-400 bg-amber-500/10 px-2 py-1 rounded border border-amber-400/20">
                            <span>⚠️</span>
                            <span>Selecione os <strong>{tiposInfo[tipoAtual as keyof typeof tiposInfo].arquivos} arquivos CSV</strong> deste tipo</span>
                        </div>
                    </div>

                    <div className="relative">
                        <input
                            type="file"
                            accept=".csv"
                            multiple
                            onChange={handleFileUpload}
                            disabled={uploading}
                            className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white/70 text-[11px] file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-[10px] file:font-bold file:bg-blue-500/20 file:text-blue-300 hover:file:bg-blue-500/30 file:cursor-pointer disabled:opacity-50"
                        />
                    </div>

                    {uploadStatus && (
                        <div className={`text-[10px] font-medium ${uploadStatus.startsWith('✓') ? 'text-emerald-400' : uploadStatus.startsWith('✗') ? 'text-red-400' : 'text-white/50'}`}>
                            {uploadStatus}
                        </div>
                    )}

                    {uploadedFiles.length > 0 && (
                        <div className="space-y-1">
                            {uploadedFiles.map((file, idx) => (
                                <div key={idx} className="flex items-center gap-2 text-[10px] text-emerald-400 bg-emerald-500/5 px-2 py-1 rounded border border-emerald-400/20">
                                    <CheckCircle2 size={10} />
                                    {file}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* Download Automático */}
            {uploadMode === 'auto' && (
                <div className="space-y-3">
                    <select
                        value={tipoEmenda}
                        onChange={(e) => setTipoEmenda(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white/70 text-[11px] focus:outline-none focus:border-purple-400/30"
                    >
                        <option value="parlamentares">Emendas Parlamentares</option>
                        <option value="transferencias">Transferências Especiais</option>
                    </select>

                    <div className="p-3 rounded-lg bg-purple-500/5 border border-purple-400/20 text-[10px] text-purple-300">
                        ⚠️ Download automático em desenvolvimento. Use upload manual por enquanto.
                    </div>
                </div>
            )}
        </div>
    );
};

export default PeleUploadPanel;
