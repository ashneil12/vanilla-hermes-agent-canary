import { type CSSProperties, useRef, useState } from 'react'

import { composerPanelCard } from '@/components/chat/composer-dock'
import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import { Kbd } from '@/components/ui/kbd'
import { Tip } from '@/components/ui/tooltip'
import { useI18n } from '@/i18n'
import { Clipboard, FileText, FolderOpen, type IconComponent, ImageIcon, Link, MessageSquareText } from '@/lib/icons'
import { cn } from '@/lib/utils'

import { GHOST_ICON_BTN } from './controls'
import type { ChatBarState } from './types'

const SNIPPET_KEYS = ['codeReview', 'implementationPlan', 'explainThis']

// Off-screen (NOT display:none) so a programmatic input.click() reliably opens
// the native file dialog — mirrors the proven selectBrowserFiles approach in
// lib/web-shim.ts (some browsers won't open a chooser for a display:none input).
const OFFSCREEN_INPUT_STYLE: CSSProperties = {
  position: 'fixed',
  left: '-9999px',
  top: '-9999px',
  opacity: 0,
  pointerEvents: 'none'
}

export function ContextMenu({
  state,
  onInsertText,
  onOpenUrlDialog,
  onPasteClipboardImage,
  onPickFiles,
  onPickFolders,
  onPickImages,
  onWebAttachFiles
}: ContextMenuProps) {
  const { t } = useI18n()
  const c = t.composer
  // Prompt snippets used to be a Radix submenu. That submenu didn't open
  // reliably when the parent menu was positioned at the bottom of the
  // window (composer "+" anchor), so we promoted it to a real Dialog —
  // easier to grow with search / descriptions, and no positioning math.
  const [snippetsOpen, setSnippetsOpen] = useState(false)

  // HermesOS hosted web: the Files/Images pickers cannot go through Radix's
  // onSelect → selectPaths → input.click() chain. onSelect fires inside Radix's
  // synthetic discrete-event dispatch, and in the cross-origin dashboard iframe
  // that synthetic boundary doesn't carry transient user-activation, so Chrome
  // silently declines to open the native file dialog (no dialog, no upload, no
  // console error). Paste/drag are unaffected because they never open a native
  // chooser. Fix: click a persistent hidden <input> from a REAL DOM onClick
  // (which keeps activation), and route the chosen File[] through the same
  // proven upload path drag-drop uses (onWebAttachFiles → attachDroppedItems).
  // Native (Electron) keeps its IPC selectPaths flow untouched.
  const isWebClient =
    typeof window !== 'undefined' &&
    Boolean((window as unknown as { __HERMES_WEB_CLIENT__?: boolean }).__HERMES_WEB_CLIENT__)
  const webAttach = isWebClient && Boolean(onWebAttachFiles)
  const filesInputRef = useRef<HTMLInputElement>(null)
  const imagesInputRef = useRef<HTMLInputElement>(null)

  const onWebInputChange = (input: HTMLInputElement | null) => {
    if (!input || !onWebAttachFiles) {
      return
    }
    const files = Array.from(input.files ?? [])
    input.value = '' // reset so re-picking the same file fires change again
    if (files.length) {
      onWebAttachFiles(files)
    }
  }

  return (
    <>
      <DropdownMenu>
        <Tip label={state.tools.label} side="top">
          <DropdownMenuTrigger asChild>
            <Button
              aria-label={state.tools.label}
              className={cn(
                GHOST_ICON_BTN,
                'data-[state=open]:bg-(--chrome-action-hover) data-[state=open]:text-foreground'
              )}
              disabled={!state.tools.enabled}
              size="icon"
              type="button"
              variant="ghost"
            >
              <Codicon name="add" size="0.875rem" />
            </Button>
          </DropdownMenuTrigger>
        </Tip>
        <DropdownMenuContent align="start" className={cn('w-60', composerPanelCard)} side="top" sideOffset={6}>
          <DropdownMenuLabel className="px-2 pb-0.5 pt-0.5 text-[0.625rem] font-semibold uppercase tracking-wider text-(--ui-text-tertiary)">
            {c.attachLabel}
          </DropdownMenuLabel>
          <ContextMenuItem
            disabled={webAttach ? false : !onPickFiles}
            icon={FileText}
            {...(webAttach
              ? { onClick: () => filesInputRef.current?.click() }
              : { onSelect: onPickFiles })}
          >
            {c.files}
          </ContextMenuItem>
          <ContextMenuItem disabled={!onPickFolders} icon={FolderOpen} onSelect={onPickFolders}>
            {c.folder}
          </ContextMenuItem>
          <ContextMenuItem
            disabled={webAttach ? false : !onPickImages}
            icon={ImageIcon}
            {...(webAttach
              ? { onClick: () => imagesInputRef.current?.click() }
              : { onSelect: onPickImages })}
          >
            {c.images}
          </ContextMenuItem>
          <ContextMenuItem
            disabled={!onPasteClipboardImage}
            icon={Clipboard}
            onSelect={onPasteClipboardImage ? () => void onPasteClipboardImage() : undefined}
          >
            {c.pasteImage}
          </ContextMenuItem>
          <ContextMenuItem icon={Link} onSelect={onOpenUrlDialog}>
            {c.url}
          </ContextMenuItem>

          <DropdownMenuSeparator />

          <ContextMenuItem icon={MessageSquareText} onSelect={() => setSnippetsOpen(true)}>
            {c.promptSnippets}
          </ContextMenuItem>

          <DropdownMenuSeparator />

          <div className="px-2 py-1 text-[0.7rem] text-muted-foreground/80">
            {c.tipPre}
            <Kbd size="sm">@</Kbd>
            {c.tipPost}
          </div>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Persistent hidden inputs live OUTSIDE DropdownMenuContent so they
          survive the menu closing on select; the web rows .click() them from a
          real DOM gesture (see the comment in ContextMenu above). */}
      {webAttach ? (
        <>
          <input
            multiple
            onChange={() => onWebInputChange(filesInputRef.current)}
            ref={filesInputRef}
            style={OFFSCREEN_INPUT_STYLE}
            tabIndex={-1}
            type="file"
          />
          <input
            accept="image/*"
            multiple
            onChange={() => onWebInputChange(imagesInputRef.current)}
            ref={imagesInputRef}
            style={OFFSCREEN_INPUT_STYLE}
            tabIndex={-1}
            type="file"
          />
        </>
      ) : null}

      <PromptSnippetsDialog onInsertText={onInsertText} onOpenChange={setSnippetsOpen} open={snippetsOpen} />
    </>
  )
}

function PromptSnippetsDialog({ onInsertText, onOpenChange, open }: PromptSnippetsDialogProps) {
  const { t } = useI18n()
  const c = t.composer

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent className="max-w-md gap-3">
        <DialogHeader>
          <DialogTitle>{c.snippetsTitle}</DialogTitle>
          <DialogDescription>{c.snippetsDesc}</DialogDescription>
        </DialogHeader>
        <ul className="grid gap-1">
          {SNIPPET_KEYS.map(key => {
            const snippet = c.snippets[key]

            return (
              <li key={key}>
                <button
                  className="group/snippet flex w-full cursor-pointer items-start gap-2.5 rounded-md border border-transparent px-2.5 py-2 text-left transition-colors hover:border-(--ui-stroke-tertiary) hover:bg-(--ui-control-hover-background) focus-visible:border-(--ui-stroke-tertiary) focus-visible:bg-(--ui-control-hover-background) focus-visible:outline-none"
                  onClick={() => {
                    onInsertText(snippet.text)
                    onOpenChange(false)
                  }}
                  type="button"
                >
                  <MessageSquareText className="mt-0.5 size-3.5 shrink-0 text-(--ui-text-tertiary) group-hover/snippet:text-foreground" />
                  <span className="grid min-w-0 gap-0.5">
                    <span className="text-sm font-medium text-foreground">{snippet.label}</span>
                    <span className="text-[length:var(--conversation-caption-font-size)] text-(--ui-text-tertiary)">
                      {snippet.description}
                    </span>
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      </DialogContent>
    </Dialog>
  )
}

export function ContextMenuItem({ children, disabled, icon: Icon, onClick, onSelect }: ContextMenuItemProps) {
  return (
    // Override font size + highlight to match the / · @ completion rows exactly.
    <DropdownMenuItem
      className="text-[length:var(--conversation-tool-font-size)] focus:bg-(--ui-bg-tertiary)"
      disabled={disabled}
      onClick={onClick}
      onSelect={onSelect}
    >
      <Icon />
      <span>{children}</span>
    </DropdownMenuItem>
  )
}

interface ContextMenuItemProps {
  children: string
  disabled?: boolean
  icon: IconComponent
  // Real DOM onClick — used for the hosted-web file pickers so input.click()
  // runs with transient user-activation (Radix onSelect's synthetic dispatch
  // loses it inside the cross-origin iframe).
  onClick?: () => void
  onSelect?: () => void
}

interface ContextMenuProps {
  onInsertText: (text: string) => void
  onOpenUrlDialog: () => void
  onPasteClipboardImage?: (opts?: { silent?: boolean }) => Promise<boolean> | void
  onPickFiles?: () => void
  onPickFolders?: () => void
  onPickImages?: () => void
  // Hosted-web only: receives File[] chosen via the persistent hidden inputs and
  // routes them through the proven attachDroppedItems upload path.
  onWebAttachFiles?: (files: File[]) => void
  state: ChatBarState
}

interface PromptSnippetsDialogProps {
  onInsertText: (text: string) => void
  onOpenChange: (open: boolean) => void
  open: boolean
}
