import { useState } from 'react'
import { applicationApi } from './api'
import { AppLayout } from './components/layout/AppLayout'
import { ApplicationForm } from './features/application/ApplicationForm'
import { DocumentManager } from './features/documents/DocumentManager'
import { AnalysisPanel } from './features/analysis/AnalysisPanel'
import type { Application, UploadedDocument } from './types/contracts'

export default function App() {
  const [application, setApplication] = useState<Application | null>(null)
  const [documents, setDocuments] = useState<UploadedDocument[]>([])

  function handleApplicationChange(next: Application | null) {
    if (next?.application_id !== application?.application_id) setDocuments([])
    setApplication(next)
  }

  async function refreshApplication() {
    if (!application) return
    const response = await applicationApi.get(application.application_id)
    setApplication(response.application)
  }

  return (
    <AppLayout>
      <ApplicationForm applicationSnapshot={application} onApplicationChange={handleApplicationChange} />
      <DocumentManager application={application} onDocumentsChange={setDocuments} onRefreshApplication={refreshApplication} />
      <AnalysisPanel application={application} documents={documents} onRefreshApplication={refreshApplication} />
    </AppLayout>
  )
}

