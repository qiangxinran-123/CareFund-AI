import { useState } from 'react'
import { applicationApi } from './api'
import { AppLayout } from './components/layout/AppLayout'
import { ApplicationForm } from './features/application/ApplicationForm'
import { DocumentManager } from './features/documents/DocumentManager'
import type { Application } from './types/contracts'

export default function App() {
  const [application, setApplication] = useState<Application | null>(null)

  async function refreshApplication() {
    if (!application) return
    const response = await applicationApi.get(application.application_id)
    setApplication(response.application)
  }

  return (
    <AppLayout>
      <ApplicationForm applicationSnapshot={application} onApplicationChange={setApplication} />
      <DocumentManager application={application} onRefreshApplication={refreshApplication} />
    </AppLayout>
  )
}

