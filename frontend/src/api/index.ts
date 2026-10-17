import { httpApplicationApi } from './application'
import { mockApplicationApi } from './applicationMock'
import { httpDocumentApi } from './documents'
import { mockDocumentApi } from './documentsMock'
import { httpAnalysisApi } from './analysis'
import { mockAnalysisApi } from './analysisMock'
import { httpDraftApi } from './draft'
import { mockDraftApi } from './draftMock'

export const isMockMode = import.meta.env.VITE_USE_MOCK_API === 'true'
export const applicationApi = isMockMode ? mockApplicationApi : httpApplicationApi
export const documentApi = isMockMode ? mockDocumentApi : httpDocumentApi
export const analysisApi = isMockMode ? mockAnalysisApi : httpAnalysisApi
export const draftApi = isMockMode ? mockDraftApi : httpDraftApi
