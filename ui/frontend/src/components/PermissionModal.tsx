import React from 'react';
import { AlertCircle } from 'lucide-react';

interface PermissionModalProps {
  isOpen: boolean;
  title: string;
  description: string;
  onAllow: () => void;
  onReject: () => void;
  onAllowInConversation: () => void;
}

/** 豆包风格浅色权限弹窗：允许 / 拒绝 / 在本对话中始终允许 */
export const PermissionModal: React.FC<PermissionModalProps> = ({
  isOpen,
  title,
  description,
  onAllow,
  onReject,
  onAllowInConversation,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/25 backdrop-blur-sm animate-fadeIn">
      <div className="bg-white border border-[#e5e6eb] rounded-2xl shadow-xl w-full max-w-md p-6 animate-slideUp">
        <div className="flex items-start gap-4 mb-5">
          <div className="p-2 bg-[#e8f0fe] rounded-xl text-[#3370ff] flex-shrink-0">
            <AlertCircle size={24} />
          </div>
          <div>
            <h3 className="text-lg font-bold text-[#1f2329] mb-1">{title}</h3>
            <p className="text-sm text-[#8f959e] leading-relaxed">{description}</p>
          </div>
        </div>

        <div className="flex flex-col gap-2 mt-6">
          <div className="flex gap-3">
            <button
              type="button"
              onClick={onReject}
              className="flex-1 px-4 py-2.5 bg-[#f2f3f5] hover:bg-[#e5e6eb] text-[#1f2329] rounded-xl text-sm font-medium transition-colors border border-[#e5e6eb]"
            >
              拒绝
            </button>
            <button
              type="button"
              onClick={onAllow}
              className="flex-1 px-4 py-2.5 bg-[#3370ff] hover:bg-[#2b5dd9] text-white rounded-xl text-sm font-medium transition-colors shadow-sm"
            >
              允许
            </button>
          </div>
          <button
            type="button"
            onClick={onAllowInConversation}
            className="w-full px-4 py-2.5 text-sm text-[#8f959e] hover:text-[#3370ff] transition-colors rounded-xl hover:bg-[#f2f3f5]"
          >
            仅在本对话中允许
          </button>
        </div>
      </div>
    </div>
  );
};
