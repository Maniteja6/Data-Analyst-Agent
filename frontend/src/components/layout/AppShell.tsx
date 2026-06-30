import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import { useUIStore } from '@/store/UiStore'
import { ChatPanel } from '@/components/chat/ChatPanel'

interface AppShellProps {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  const { chatOpen } = useUIStore()

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <TopBar />
        <main className="flex-1 overflow-auto p-5">
          {children}
        </main>
      </div>
      {chatOpen && (
        <div className="w-96 flex-shrink-0 border-l border-dp-border bg-dp-surface flex flex-col">
          <ChatPanel />
        </div>
      )}
    </div>
  )
}