import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import { BrowseDatasets } from './pages/BrowseDatasets';
import { RunPipeline } from './pages/RunPipeline';
import { JobStatus } from './pages/JobStatus';
import { DatasetDetail } from './pages/DatasetDetail';
import { PipelineWizard } from './pages/PipelineWizard';
import { MyDrafts } from './pages/MyDrafts';
import { Toaster } from './components/ui/sonner';
import { AlertDialogProvider } from './hooks/useAlertDialog';
import { ConfirmDialogProvider } from './hooks/useConfirmDialog';
import { cn } from './lib/utils';
import './index.css';

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      refetchOnWindowFocus: false,
    },
  },
});

function Navigation() {
  const location = useLocation();

  return (
    <header className="border-b">
      <div className="container mx-auto px-4 py-4">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold">Sensor Data Processor</h1>
          <nav className="flex gap-4">
            <Link
              to="/"
              className={cn(
                "text-sm font-medium hover:underline",
                location.pathname === '/' ? '' : 'text-muted-foreground'
              )}
            >
              Browse Datasets
            </Link>
            <Link
              to="/run"
              className={cn(
                "text-sm font-medium hover:underline",
                location.pathname === '/run' ? '' : 'text-muted-foreground'
              )}
            >
              Run Pipeline
            </Link>
            <Link
              to="/drafts"
              className={cn(
                "text-sm font-medium hover:underline",
                location.pathname === '/drafts' ? '' : 'text-muted-foreground'
              )}
            >
              My Drafts
            </Link>
          </nav>
        </div>
      </div>
    </header>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AlertDialogProvider>
        <ConfirmDialogProvider>
          <BrowserRouter>
            <div className="min-h-screen bg-background">
              <Navigation />
              <main>
                <Routes>
                  <Route path="/" element={<BrowseDatasets />} />
                  <Route path="/run" element={<RunPipeline />} />
                  <Route path="/drafts" element={<MyDrafts />} />
                  <Route path="/jobs/:jobId" element={<JobStatus />} />
                  <Route path="/sessions/:sessionId/wizard" element={<PipelineWizard />} />
                  <Route path="/datasets/:id" element={<DatasetDetail />} />
                </Routes>
              </main>
              <Toaster />
            </div>
          </BrowserRouter>
        </ConfirmDialogProvider>
      </AlertDialogProvider>
    </QueryClientProvider>
  );
}

export default App;
