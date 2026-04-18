import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BookOpen, ExternalLink, FolderOpen, RefreshCw, Save, Upload } from 'lucide-react';
import { useAppState } from '../hooks/useAppState';
import {
  createGraphExtensionsApi,
  type CreateGraphExperienceLibraryEntry,
  type CreateGraphExperienceLibraryFileResponse,
  type CreateGraphExperienceLibraryOverviewResponse,
} from '../services/create-graph-extensions';

const formatTimestamp = (value?: string | null): string => {
  if (!value) return '未知时间';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
};

export const ExperienceLibraryManagerPanel = () => {
  const { projectName, availableRepos } = useAppState();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [overview, setOverview] = useState<CreateGraphExperienceLibraryOverviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingFile, setLoadingFile] = useState(false);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [selectedRelativePath, setSelectedRelativePath] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<CreateGraphExperienceLibraryFileResponse | null>(null);
  const [editorContent, setEditorContent] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  const activeProjectPath = useMemo(() => {
    if (availableRepos.length === 0) return undefined;
    const matchedPath = projectName
      ? availableRepos.find((repo) => repo.name === projectName)?.path
      : undefined;
    if (matchedPath) return matchedPath;
    if (availableRepos.length === 1) return availableRepos[0].path;
    return undefined;
  }, [availableRepos, projectName]);

  const entries = overview?.entries ?? [];
  const selectedEntry = useMemo(
    () => entries.find((entry) => entry.relativePath === selectedRelativePath) ?? null,
    [entries, selectedRelativePath],
  );
  const isDirty = selectedFile !== null && editorContent !== selectedFile.content;

  const loadLibrary = useCallback(async (preferredRelativePath?: string) => {
    if (!activeProjectPath) {
      setOverview(null);
      setSelectedRelativePath('');
      setSelectedFile(null);
      setEditorContent('');
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const payload = await createGraphExtensionsApi.fetchExperienceLibrary('/api', activeProjectPath);
      setOverview(payload);
      const nextRelativePath = preferredRelativePath && payload.entries.some((entry) => entry.relativePath === preferredRelativePath)
        ? preferredRelativePath
        : payload.entries[0]?.relativePath || '';
      setSelectedRelativePath(nextRelativePath);
    } catch (loadError) {
      setOverview(null);
      setSelectedRelativePath('');
      setSelectedFile(null);
      setEditorContent('');
      setError(loadError instanceof Error ? loadError.message : String(loadError));
    } finally {
      setLoading(false);
    }
  }, [activeProjectPath]);

  const loadFile = useCallback(async (relativePath: string) => {
    if (!activeProjectPath || !relativePath) {
      setSelectedFile(null);
      setEditorContent('');
      setFileError(null);
      return;
    }

    setLoadingFile(true);
    setFileError(null);
    setSaveMessage(null);
    try {
      const payload = await createGraphExtensionsApi.readExperienceLibraryFile('/api', activeProjectPath, relativePath);
      setSelectedFile(payload);
      setEditorContent(payload.content);
    } catch (loadError) {
      setSelectedFile(null);
      setEditorContent('');
      setFileError(loadError instanceof Error ? loadError.message : String(loadError));
    } finally {
      setLoadingFile(false);
    }
  }, [activeProjectPath]);

  useEffect(() => {
    void loadLibrary();
  }, [loadLibrary]);

  useEffect(() => {
    if (!selectedRelativePath) {
      setSelectedFile(null);
      setEditorContent('');
      setFileError(null);
      return;
    }
    void loadFile(selectedRelativePath);
  }, [loadFile, selectedRelativePath]);

  const handleOpenFolder = useCallback(async () => {
    if (!overview?.experiencePathsDir) return;
    try {
      await createGraphExtensionsApi.openFileSystemPath('/api', overview.experiencePathsDir);
    } catch (openError) {
      setError(openError instanceof Error ? openError.message : String(openError));
    }
  }, [overview?.experiencePathsDir]);

  const handleOpenCurrentFile = useCallback(async () => {
    if (!selectedEntry?.absolutePath) return;
    try {
      await createGraphExtensionsApi.openFileSystemPath('/api', selectedEntry.absolutePath);
    } catch (openError) {
      setFileError(openError instanceof Error ? openError.message : String(openError));
    }
  }, [selectedEntry?.absolutePath]);

  const handleSave = useCallback(async () => {
    if (!activeProjectPath || !selectedFile) return;
    setSaving(true);
    setFileError(null);
    setSaveMessage(null);
    try {
      const response = await createGraphExtensionsApi.saveExperienceLibraryFile('/api', {
        project_path: activeProjectPath,
        relative_path: selectedFile.relativePath,
        content: editorContent,
        etag: selectedFile.etag,
      });
      setSaveMessage('已保存');
      await loadLibrary(selectedFile.relativePath);
      const reloaded = await createGraphExtensionsApi.readExperienceLibraryFile('/api', activeProjectPath, selectedFile.relativePath);
      setSelectedFile(reloaded);
      setEditorContent(reloaded.content);
      if (!response.ok) {
        setFileError('保存未成功完成');
      }
    } catch (saveError) {
      setFileError(saveError instanceof Error ? saveError.message : String(saveError));
    } finally {
      setSaving(false);
    }
  }, [activeProjectPath, editorContent, loadLibrary, selectedFile]);

  const handleImportClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleImportFiles = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(event.target.files ?? []);
    event.target.value = '';
    if (!activeProjectPath || selectedFiles.length === 0) return;

    setImporting(true);
    setError(null);
    try {
      await createGraphExtensionsApi.importExperienceLibraryFiles('/api', activeProjectPath, selectedFiles);
      await loadLibrary();
    } catch (importError) {
      setError(importError instanceof Error ? importError.message : String(importError));
    } finally {
      setImporting(false);
    }
  }, [activeProjectPath, loadLibrary]);

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".json,.md,text/markdown,application/json"
        className="hidden"
        onChange={handleImportFiles}
      />

      <div className="px-4 py-3 border-b border-border-subtle bg-elevated/40 flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-amber-100">经验库管理器</div>
          <div className="text-xs text-text-muted">在分析界面直接查看、编辑、导入项目经验库。</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => { void loadLibrary(selectedRelativePath); }}
            className="p-1.5 rounded text-text-muted hover:text-text-primary hover:bg-hover"
            title="刷新经验库"
            disabled={loading}
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            onClick={handleOpenFolder}
            className="px-2.5 py-1.5 rounded border border-border-subtle text-xs text-text-secondary hover:text-text-primary hover:bg-hover flex items-center gap-1.5"
            disabled={!overview?.experiencePathsDir}
          >
            <FolderOpen className="w-3.5 h-3.5" /> 打开经验库文件夹
          </button>
          <button
            type="button"
            onClick={handleImportClick}
            className="px-2.5 py-1.5 rounded border border-amber-400/30 bg-amber-500/10 text-xs text-amber-100 hover:bg-amber-500/20 flex items-center gap-1.5"
            disabled={!activeProjectPath || importing}
          >
            <Upload className="w-3.5 h-3.5" /> {importing ? '导入中' : '导入本地 json/md'}
          </button>
        </div>
      </div>

      <div className="px-4 py-3 border-b border-border-subtle bg-surface/40">
        {!activeProjectPath ? (
          <div className="text-sm text-text-muted">当前未解析到项目路径，无法加载经验库。</div>
        ) : (
          <div className="grid grid-cols-4 gap-3">
            <div className="rounded-lg border border-border-subtle bg-elevated/30 p-3">
              <div className="text-[11px] text-text-muted uppercase tracking-wide">经验天数</div>
              <div className="mt-1 text-xl font-semibold text-amber-100">{overview?.summary.experienceDays ?? 0}</div>
            </div>
            <div className="rounded-lg border border-border-subtle bg-elevated/30 p-3">
              <div className="text-[11px] text-text-muted uppercase tracking-wide">总文件</div>
              <div className="mt-1 text-xl font-semibold text-text-primary">{overview?.summary.totalFiles ?? 0}</div>
            </div>
            <div className="rounded-lg border border-border-subtle bg-elevated/30 p-3">
              <div className="text-[11px] text-text-muted uppercase tracking-wide">生成文件</div>
              <div className="mt-1 text-xl font-semibold text-cyan-200">{overview?.summary.generatedFiles ?? 0}</div>
            </div>
            <div className="rounded-lg border border-border-subtle bg-elevated/30 p-3">
              <div className="text-[11px] text-text-muted uppercase tracking-wide">导入文件</div>
              <div className="mt-1 text-xl font-semibold text-emerald-200">{overview?.summary.importedFiles ?? 0}</div>
            </div>
          </div>
        )}
        {error && <div className="mt-3 text-sm text-rose-300">{error}</div>}
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-[280px_minmax(0,1fr)] overflow-hidden">
        <div className="border-r border-border-subtle overflow-y-auto p-3 space-y-2">
          {loading && entries.length === 0 && <div className="text-sm text-text-muted">正在加载经验库...</div>}
          {!loading && entries.length === 0 && <div className="text-sm text-text-muted">还没有经验库文件，可先导入 `.json` / `.md`。</div>}
          {entries.map((entry: CreateGraphExperienceLibraryEntry) => {
            const active = entry.relativePath === selectedRelativePath;
            return (
              <button
                key={entry.relativePath}
                type="button"
                onClick={() => setSelectedRelativePath(entry.relativePath)}
                className={`w-full text-left rounded-lg border px-3 py-2.5 transition-colors ${active
                  ? 'border-amber-400/40 bg-amber-500/10'
                  : 'border-border-subtle bg-surface/40 hover:bg-hover'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium text-text-primary truncate">{entry.filename}</div>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border ${entry.type === 'generated'
                    ? 'border-cyan-400/30 text-cyan-200 bg-cyan-500/10'
                    : 'border-emerald-400/30 text-emerald-200 bg-emerald-500/10'
                  }`}>{entry.type === 'generated' ? '生成' : '导入'}</span>
                </div>
                <div className="mt-1 text-[11px] text-text-muted">日期：{entry.day}</div>
                <div className="mt-1 text-[11px] text-text-muted">更新：{formatTimestamp(entry.updatedAt)}</div>
              </button>
            );
          })}
        </div>

        <div className="min-h-0 flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-border-subtle bg-elevated/30 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="text-sm font-medium text-text-primary truncate">{selectedEntry?.filename || '未选择文件'}</div>
              <div className="text-xs text-text-muted truncate">
                {selectedEntry ? `${selectedEntry.day} · ${formatTimestamp(selectedEntry.updatedAt)}` : '选择左侧文件后可查看和编辑内容'}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleOpenCurrentFile}
                className="px-2.5 py-1.5 rounded border border-border-subtle text-xs text-text-secondary hover:text-text-primary hover:bg-hover flex items-center gap-1.5"
                disabled={!selectedEntry}
              >
                <ExternalLink className="w-3.5 h-3.5" /> 打开当前文件
              </button>
              <button
                type="button"
                onClick={() => { void handleSave(); }}
                className="px-2.5 py-1.5 rounded border border-amber-400/30 bg-amber-500/10 text-xs text-amber-100 hover:bg-amber-500/20 flex items-center gap-1.5 disabled:opacity-50"
                disabled={!selectedFile || !isDirty || saving}
              >
                <Save className="w-3.5 h-3.5" /> {saving ? '保存中' : '保存'}
              </button>
            </div>
          </div>

          <div className="px-4 py-2 border-b border-border-subtle bg-surface/30 flex items-center gap-3 text-xs text-text-muted">
            <span className="flex items-center gap-1"><BookOpen className="w-3.5 h-3.5" /> {selectedEntry?.type === 'generated' ? '系统生成文件' : selectedEntry?.type === 'imported' ? '用户导入文件' : '经验库文件'}</span>
            {saveMessage && <span className="text-emerald-300">{saveMessage}</span>}
            {fileError && <span className="text-rose-300">{fileError}</span>}
          </div>

          <div className="flex-1 min-h-0 p-4 overflow-hidden">
            {loadingFile ? (
              <div className="text-sm text-text-muted">正在加载文件内容...</div>
            ) : selectedFile ? (
              <textarea
                value={editorContent}
                onChange={(event) => {
                  setEditorContent(event.target.value);
                  setSaveMessage(null);
                }}
                spellCheck={false}
                className="w-full h-full resize-none rounded-lg border border-border-subtle bg-surface px-3 py-3 text-sm text-text-primary font-mono outline-none focus:border-amber-400/40"
              />
            ) : (
              <div className="h-full rounded-lg border border-dashed border-border-subtle flex items-center justify-center text-sm text-text-muted">
                选择经验库文件后可查看并编辑 JSON 内容。
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
