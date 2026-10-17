import { httpApplicationApi } from './application'
import { mockApplicationApi } from './applicationMock'
import { httpDocumentApi } from './documents'
import { mockDocumentApi } from './documentsMock'

export const isMockMode = import.meta.env.VITE_USE_MOCK_API === 'true'
export const applicationApi = isMockMode ? mockApplicationApi : httpApplicationApi
export const documentApi = isMockMode ? mockDocumentApi : httpDocumentApi
