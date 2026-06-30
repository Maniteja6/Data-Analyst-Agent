import { create } from 'zustand'

type ActivePage =
  | 'dashboard'
  | 'data-insights'
  | 'predictive-analysis'
  | 'data-quality'
  | 'ai-insights'
  | 'export-results'

interface UIState {
  sidebarCollapsed: boolean
  activePage: ActivePage
  chatOpen: boolean
  setSidebarCollapsed: (v: boolean) => void
  setActivePage: (page: ActivePage) => void
  setChatOpen: (v: boolean) => void
  toggleSidebar: () => void
  toggleChat: () => void
}

export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  activePage: 'dashboard',
  chatOpen: false,
  setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
  setActivePage: (activePage) => set({ activePage }),
  setChatOpen: (chatOpen) => set({ chatOpen }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  toggleChat: () => set((s) => ({ chatOpen: !s.chatOpen })),
}))