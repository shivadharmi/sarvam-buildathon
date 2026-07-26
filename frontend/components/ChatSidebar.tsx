"use client";

import { answerCount, isEmpty, titleFor, type Conversation } from "@/lib/conversations";
import { DOCUMENT_LABELS } from "@/lib/questions";

interface ChatSidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onClearAll: () => void;
}

/**
 * Past conversations, newest first.
 *
 * Each entry shows which page it was about — the two documents are in
 * different scripts, and a Tamil title next to a Telugu one is otherwise the
 * only clue, which is not enough for someone who reads neither.
 */
export function ChatSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onClearAll,
}: ChatSidebarProps) {
  const saved = conversations.filter((conversation) => !isEmpty(conversation));

  return (
    <aside
      className="flex flex-col border-b border-rule lg:min-h-0 lg:border-r lg:border-b-0"
      aria-label="Chat history"
    >
      <div className="shrink-0 px-3 py-3">
        <button
          type="button"
          onClick={onNew}
          className="w-full border border-ink px-3 py-2 text-xs font-medium transition-colors hover:bg-ink hover:text-paper"
        >
          + New chat
        </button>
      </div>

      <div className="flex-1 px-1 lg:min-h-0 lg:overflow-y-auto">
        {saved.length === 0 ? (
          <p className="px-3 py-2 text-xs leading-relaxed text-faint">
            Your chats appear here once you ask something.
          </p>
        ) : (
          <>
            <p className="eyebrow px-3 pt-2 pb-1">History · {saved.length}</p>
            <ul>
              {saved.map((conversation) => {
                const isActive = conversation.id === activeId;
                return (
                  <li key={conversation.id} className="group relative">
                    <button
                      type="button"
                      onClick={() => onSelect(conversation.id)}
                      aria-current={isActive ? "true" : undefined}
                      className={`w-full px-3 py-2 pr-7 text-left transition-colors ${
                        isActive ? "bg-surface" : "hover:bg-surface/60"
                      }`}
                    >
                      <span className="font-indic block truncate text-xs leading-snug text-ink">
                        {titleFor(conversation)}
                      </span>
                      <span className="mt-0.5 block text-xs text-faint">
                        {DOCUMENT_LABELS[conversation.docId]?.script ?? conversation.docId}
                        {" · "}
                        {answerCount(conversation)}{" "}
                        {answerCount(conversation) === 1 ? "answer" : "answers"}
                      </span>
                    </button>

                    <button
                      type="button"
                      onClick={() => onDelete(conversation.id)}
                      aria-label={`Delete chat: ${titleFor(conversation)}`}
                      className="absolute top-2 right-2 px-1 text-xs text-faint opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 hover:text-seal"
                    >
                      ✕
                    </button>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>

      {saved.length > 0 && (
        <div className="shrink-0 border-t border-rule-soft px-3 py-2">
          <button
            type="button"
            onClick={onClearAll}
            className="text-xs text-faint underline-offset-2 hover:text-seal hover:underline"
          >
            Clear all chats
          </button>
        </div>
      )}
    </aside>
  );
}
