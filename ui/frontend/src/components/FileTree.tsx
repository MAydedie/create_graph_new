
import React, { useState, useEffect } from 'react';
import { Folder, File, ChevronRight, ChevronDown, Loader2, AlertCircle } from 'lucide-react';
import { api, FileItem } from '../services/api';
import clsx from 'clsx';

interface FileTreeProps {
    rootPath: string;
    onSelectFile: (path: string) => void;
    selectedFile: string | null;
}

const FileSystemItem: React.FC<{
    item: FileItem;
    level: number;
    onSelect: (path: string) => void;
    selectedFile: string | null;
}> = ({ item, level, onSelect, selectedFile }) => {
    const [isOpen, setIsOpen] = useState(false);
    const [children, setChildren] = useState<FileItem[]>([]);
    const [loading, setLoading] = useState(false);

    const isDirectory = item.type === 'directory';
    const paddingLeft = `${level * 12}px`;

    const handleToggle = async (e: React.MouseEvent) => {
        e.stopPropagation();
        if (!isDirectory) {
            onSelect(item.path);
            return;
        }

        if (!isOpen && children.length === 0) {
            setLoading(true);
            try {
                const items = await api.listFiles(item.path);
                const sorted = items.sort((a, b) => {
                    if (a.type === b.type) return a.name.localeCompare(b.name);
                    return a.type === 'directory' ? -1 : 1;
                });
                setChildren(sorted);
            } catch (err) {
                console.error("Load files failed", err);
            } finally {
                setLoading(false);
            }
        }
        setIsOpen(!isOpen);
    };

    return (
        <div>
            <div
                className={clsx(
                    "flex items-center py-1 px-2 cursor-pointer transition-colors text-xs rounded-sm mx-1 select-none",
                    selectedFile === item.path ? "bg-zinc-800 text-zinc-100 font-medium" : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
                )}
                style={{ paddingLeft }}
                onClick={handleToggle}
            >
                <div className="mr-1.5 opacity-70 shrink-0">
                    {isDirectory ? (
                        isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />
                    ) : (
                        <div className="w-3.5" />
                    )}
                </div>
                <div className="mr-2 shrink-0 opacity-80">
                    {isDirectory ? <Folder size={14} className="text-zinc-500" /> : <File size={14} />}
                </div>
                <span className="truncate">{item.name}</span>
                {loading && <Loader2 size={12} className="ml-2 animate-spin opacity-50" />}
            </div>

            {isOpen && (
                <div className="border-l border-zinc-800/50 ml-[18px]">
                    {children.map((child) => (
                        <FileSystemItem
                            key={child.path}
                            item={child}
                            level={level + 1}
                            onSelect={onSelect}
                            selectedFile={selectedFile}
                        />
                    ))}
                </div>
            )}
        </div>
    );
};

export const FileTree: React.FC<FileTreeProps> = ({ rootPath, onSelectFile, selectedFile }) => {
    const [rootItems, setRootItems] = useState<FileItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!rootPath) return;

        setLoading(true);
        setError(null);
        setRootItems([]);

        api.listFiles(rootPath).then(items => {
            const sorted = items.sort((a, b) => {
                if (a.type === b.type) return a.name.localeCompare(b.name);
                return a.type === 'directory' ? -1 : 1;
            });
            setRootItems(sorted);
        }).catch(err => {
            console.error(err);
            const msg = err.response?.data?.detail || err.message || "Failed to load directory";
            setError(msg);
        }).finally(() => {
            setLoading(false);
        });
    }, [rootPath]);

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center pt-10 text-zinc-500 gap-2">
                <Loader2 size={16} className="animate-spin" />
                <span className="text-[10px]">Loading workspace...</span>
            </div>
        );
    }

    if (error) {
        return (
            <div className="p-4 flex flex-col items-center text-center">
                <AlertCircle size={24} className="text-red-500/50 mb-2" />
                <span className="text-xs text-red-400 font-medium break-all">{error}</span>
                <p className="text-[10px] text-zinc-600 mt-2">Check if the path exists.</p>
            </div>
        );
    }

    if (rootItems.length === 0) {
        return (
            <div className="p-8 text-center">
                <span className="text-xs text-zinc-600 block">Empty folder</span>
                <span className="text-[10px] text-zinc-700 block mt-1 break-all opacity-50">{rootPath}</span>
            </div>
        );
    }

    return (
        <div className="h-full overflow-y-auto pb-10">
            <div className="pb-4 pt-2">
                {rootItems.map((item) => (
                    <FileSystemItem
                        key={item.path}
                        item={item}
                        level={1}
                        onSelect={onSelectFile}
                        selectedFile={selectedFile}
                    />
                ))}
            </div>
        </div>
    );
};
