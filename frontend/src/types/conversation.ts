export type MessageRole = 'user' | 'assistant'

export interface Citation {
  text: string
  source: string
  columnName?: string
}

export interface VegaLiteSpec {
  $schema: string
  mark: string
  data: { values: Record<string, unknown>[] }
  encoding: Record<string, unknown>
  width?: number
  height?: number
}

export interface ChatVisualizationPayload {
  type: 'vega'
  spec: VegaLiteSpec
  caption?: string
}

export interface Message {
  id: string
  role: MessageRole
  content: string
  citations?: Citation[]
  visualizations?: ChatVisualizationPayload[]
  isStreaming?: boolean
  createdAt: string
}

export interface Conversation {
  id: string
  datasetId: string
  title: string
  messages: Message[]
  createdAt: string
  updatedAt: string
}