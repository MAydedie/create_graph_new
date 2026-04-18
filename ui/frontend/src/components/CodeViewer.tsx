
import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
// @ts-ignore
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
// @ts-ignore
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface CodeViewerProps {
    filePath: string | null;
}

export const CodeViewer: React.FC<CodeViewerProps> = ({ filePath }) => {
    const [content, setContent] = useState<string>("");
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!filePath) return;
        setLoading(true);
        api.readFile(filePath)
            .then(data => setContent(data.content))
            .catch(err => setContent(`Error reading file: ${err}`))
            .finally(() => setLoading(false));
    }, [filePath]);

    if (!filePath) {
        return (
            <div className="h-full flex items-center justify-center text-zinc-600 bg-zinc-950/50">
                <div className="text-center">
                    <div className="text-4xl mb-4">⌘</div>
                    <p>Select a file to view content</p>
                </div>
            </div>
        );
    }

    const extension = filePath.split('.').pop() || 'text';

    return (
        <div className="h-full flex flex-col bg-[#1e1e1e]">
            <div className="flex items-center px-4 py-2 bg-surface border-b border-border shadow-sm">
                <span className="text-sm font-medium text-zinc-300">{filePath}</span>
                {loading && <span className="ml-2 text-xs text-zinc-500">Loading...</span>}
            </div>
            <div className="flex-1 overflow-auto custom-scrollbar">
                <SyntaxHighlighter
                    language={extension}
                    style={vscDarkPlus}
                    customStyle={{ margin: 0, padding: '1.5rem', background: 'transparent', fontSize: '14px' }}
                    showLineNumbers={true}
                >
                    {content}
                </SyntaxHighlighter>
            </div>
        </div>
    );
};
