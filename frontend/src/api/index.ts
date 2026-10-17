import { httpApplicationApi } from './application'
import { mockApplicationApi } from './applicationMock'

export const isMockMode = import.meta.env.VITE_USE_MOCK_API === 'true'
export const applicationApi = isMockMode ? mockApplicationApi : httpApplicationApi
