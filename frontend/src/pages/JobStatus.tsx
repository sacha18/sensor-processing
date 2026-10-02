import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useJobStatus, useCancelJob, usePublishDataset } from '../api/hooks';
import { useAlertDialog } from '../hooks/useAlertDialog';
import { useConfirmDialog } from '../hooks/useConfirmDialog';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import {
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  Play,
  Download,
  Upload as UploadIcon,
  X,
  ArrowLeft,
  Workflow,
} from 'lucide-react';

export function JobStatus() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { data: job, isLoading } = useJobStatus(jobId || null);
  const cancelJob = useCancelJob();
  const { showAlert } = useAlertDialog();
  const { confirm } = useConfirmDialog();

  // State for publishing
  const [showPublish, setShowPublish] = useState(false);
  const [publishTitle, setPublishTitle] = useState('');
  const [publishDescription, setPublishDescription] = useState('');
  const [publishTags, setPublishTags] = useState('');
  const publishMutation = usePublishDataset();

  // Auto-navigate to home if job doesn't exist
  useEffect(() => {
    if (!isLoading && !job) {
      setTimeout(() => navigate('/'), 3000);
    }
  }, [isLoading, job, navigate]);

  // Show publish form when job finishes successfully
  useEffect(() => {
    if (job?.status === 'finished' && job.result?.session_id) {
      setShowPublish(true);
      // Auto-generate title from session_id
      setPublishTitle(`Dataset ${job.result.session_id.substring(0, 8)}`);
    }
  }, [job?.status, job?.result?.session_id]);

  const handleCancel = async () => {
    if (!jobId) return;

    const confirmed = await confirm({
      title: 'Cancel Job',
      message: 'Are you sure you want to cancel this job?',
      confirmText: 'Cancel Job',
      variant: 'destructive',
    });

    if (!confirmed) return;

    try {
      await cancelJob.mutateAsync(jobId);
    } catch (error) {
      console.error('Failed to cancel job:', error);
    }
  };

  const handlePublish = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!job?.result?.session_id) return;

    try {
      const result = await publishMutation.mutateAsync({
        session_id: job.result.session_id,
        title: publishTitle,
        description: publishDescription,
        pipeline_type: job.result.pipeline_type || 'tms',
        created_by: job.result.user || 'anonymous',
        tags: publishTags.split(',').map(t => t.trim()).filter(Boolean),
      });

      showAlert({
        variant: 'success',
        message: `Dataset published! ID: ${result.dataset_id}`,
      });
      navigate('/');
    } catch (error) {
      console.error('Failed to publish dataset:', error);
      showAlert({
        variant: 'error',
        message: 'Failed to publish dataset. Check console for details.',
      });
    }
  };

  if (isLoading) {
    return (
      <div className="container mx-auto py-8 max-w-4xl">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="container mx-auto py-8 max-w-4xl">
        <Card>
          <CardHeader>
            <CardTitle>Job Not Found</CardTitle>
            <CardDescription>
              Job ID {jobId} doesn't exist. Redirecting to home...
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  const statusIcon = {
    queued: <Clock className="h-5 w-5 text-muted-foreground" />,
    started: <Play className="h-5 w-5 text-blue-500" />,
    running: <Loader2 className="h-5 w-5 animate-spin text-blue-500" />,
    finished: <CheckCircle2 className="h-5 w-5 text-green-500" />,
    failed: <XCircle className="h-5 w-5 text-red-500" />,
    canceled: <X className="h-5 w-5 text-muted-foreground" />,
  }[job.status] || <Clock className="h-5 w-5" />;

  const statusBadge = {
    queued: <Badge variant="outline">Queued</Badge>,
    started: <Badge className="bg-blue-500">Started</Badge>,
    running: <Badge className="bg-blue-500">Running</Badge>,
    finished: <Badge className="bg-green-500">Finished</Badge>,
    failed: <Badge variant="destructive">Failed</Badge>,
    canceled: <Badge variant="outline">Canceled</Badge>,
  }[job.status] || <Badge>Unknown</Badge>;

  const progress = job.meta?.progress || 0;
  const currentStage = job.meta?.current_stage || 'Initializing...';

  return (
    <div className="container mx-auto py-8 max-w-4xl">
      <div className="mb-6">
        <Link to="/run" className="text-sm text-muted-foreground hover:underline flex items-center gap-1 mb-2">
          <ArrowLeft className="h-4 w-4" />
          Back to Run Pipeline
        </Link>
        <h1 className="text-3xl font-bold mb-2">Job Status</h1>
        <p className="text-muted-foreground font-mono text-sm">ID: {jobId}</p>
      </div>

      <div className="space-y-6">
        {/* Status Card */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {statusIcon}
                <CardTitle>Pipeline Execution</CardTitle>
              </div>
              {statusBadge}
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Progress Bar */}
            {(job.status === 'running' || job.status === 'started') && (
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">{currentStage}</span>
                  <span className="font-medium">{progress}%</span>
                </div>
                <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all duration-300"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            )}

            {/* Job Details */}
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground">Status</p>
                <p className="font-medium capitalize">{job.status}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Started</p>
                <p className="font-medium">
                  {job.started_at ? new Date(job.started_at).toLocaleString() : 'Not started'}
                </p>
              </div>
              {job.ended_at && (
                <div>
                  <p className="text-muted-foreground">Ended</p>
                  <p className="font-medium">{new Date(job.ended_at).toLocaleString()}</p>
                </div>
              )}
              {job.result?.session_id && (
                <div>
                  <p className="text-muted-foreground">Session ID</p>
                  <p className="font-mono text-xs">{job.result.session_id}</p>
                </div>
              )}
            </div>

            {/* Error Message */}
            {job.status === 'failed' && job.exc_info && (
              <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-md">
                <p className="text-sm font-medium text-destructive mb-1">Error:</p>
                <p className="text-sm text-destructive/80 font-mono">{job.exc_info}</p>
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2">
              {(job.status === 'queued' || job.status === 'running' || job.status === 'started') && (
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={handleCancel}
                  disabled={cancelJob.isPending}
                >
                  {cancelJob.isPending ? 'Canceling...' : 'Cancel Job'}
                </Button>
              )}

              {job.status === 'finished' && job.result?.session_id && (
                <>
                  <Button
                    size="sm"
                    variant="default"
                    onClick={() => navigate(`/sessions/${job.result.session_id}/wizard`)}
                  >
                    <Workflow className="h-4 w-4 mr-2" />
                    View Pipeline Steps
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      const url = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/sessions/${job.result.session_id}/download`;
                      window.open(url, '_blank');
                    }}
                  >
                    <Download className="h-4 w-4 mr-2" />
                    Download Result
                  </Button>
                </>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Publish Dataset Form */}
        {showPublish && job.status === 'finished' && job.result?.session_id && (
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <UploadIcon className="h-5 w-5" />
                <CardTitle>Publish Dataset</CardTitle>
              </div>
              <CardDescription>
                Make this processed dataset available for browsing and download
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handlePublish} className="space-y-4">
                <div>
                  <label className="text-sm font-medium mb-1 block">Title *</label>
                  <Input
                    required
                    value={publishTitle}
                    onChange={(e) => setPublishTitle(e.target.value)}
                    placeholder="My Processed Dataset"
                  />
                </div>

                <div>
                  <label className="text-sm font-medium mb-1 block">Description</label>
                  <Input
                    value={publishDescription}
                    onChange={(e) => setPublishDescription(e.target.value)}
                    placeholder="Brief description of this dataset"
                  />
                </div>

                <div>
                  <label className="text-sm font-medium mb-1 block">
                    Tags (comma-separated)
                  </label>
                  <Input
                    value={publishTags}
                    onChange={(e) => setPublishTags(e.target.value)}
                    placeholder="production, site-A, 2024"
                  />
                </div>

                <div className="flex justify-end gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setShowPublish(false)}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" disabled={publishMutation.isPending}>
                    {publishMutation.isPending ? 'Publishing...' : 'Publish Dataset'}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
