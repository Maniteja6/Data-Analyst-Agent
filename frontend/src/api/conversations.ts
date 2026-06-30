import { apiClient } from './client'
import type { Conversation, Message } from '@/types/conversation'

export const conversationsApi = {
  create: async (datasetId: string): Promise<Conversation> => {
    const { data } = await apiClient.post<Conversation>('/conversations', { datasetId })
    return data
  },

  get: async (conversationId: string): Promise<Conversation> => {
    const { data } = await apiClient.get<Conversation>(`/conversations/${conversationId}`)
    return data
  },

  sendMessage: async (conversationId: string, content: string): Promise<Message> => {
    const { data } = await apiClient.post<Message>(
      `/conversations/${conversationId}/messages`,
      { content },
    )
    return data
  },
}