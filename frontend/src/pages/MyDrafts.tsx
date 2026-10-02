import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useConfirmDialog } from '../hooks/useConfirmDialog';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { FileEdit, Trash2, Calendar, Database, ArrowRight, AlertCircle, Loader2, CheckCircle, XCircle } from 'lucide-react';
import { Alert, AlertDescription } from '../components/ui/alert';
import { useSessionProgress, useSessionStatus, useListSessions, useDeleteSession } from '../api/hooks';
import { toast } from 'sonner';

interface DraftSession {
  sessionId: string;
  pipelineType: string;
  lastModified: string;
  keys: string[];
  currentStep?: string;
}

// Separate component for each draft to use hooks
function DraftCard({
  draft,
  onResume,
  onDelete
}: {
  draft: DraftSession;
  onResume: (draft: DraftSession) => void;
  onDelete: (sessionId: string, pipelineType: string) => void;
}) {
  // Use the session progress hook for real-time updates
  const progress = useSessionProgress(draft.sessionId, draft.pipelineType);

  // Use session status hook for automated runs
  const { data: sessionStatus } = useSessionStatus(
    draft.sessionId,
    draft.pipelineType,
    true // Always enabled for draft cards
  );

  // Determine status for badge display
  const status = sessionStatus?.status ?? 'manual';
  const isAutomated = status !== 'manual';

  // For automated runs, prioritize sessionStatus data over localStorage-based progress
  // For manual runs, use the wizard progress hook
  let displayProgress = isAutomated
    ? (sessionStatus?.progress ?? getProgressPercentageStatic(draft))
    : (progress?.overallProgress ?? sessionStatus?.progress ?? getProgressPercentageStatic(draft));

  // Force 100% progress for completed runs
  if (status === 'completed') {
    displayProgress = 100;
  }

  const currentStepName = isAutomated
    ? (sessionStatus?.current_stage ?? getStepNameStatic(draft))
    : (progress?.currentStep ?? sessionStatus?.current_stage ?? getStepNameStatic(draft));

  const isJobRunning = isAutomated
    ? (sessionStatus?.status === 'processing' || sessionStatus?.status === 'queued')
    : (progress?.isJobRunning ?? (sessionStatus?.status === 'processing' || sessionStatus?.status === 'queued'));

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <CardTitle className="flex items-center gap-2">
              <FileEdit className="h-5 w-5" />
              <span className="font-mono text-sm">{draft.sessionId}</span>
            </CardTitle>
            <div className="mt-2 flex items-center gap-4 flex-wrap">
              <span className="flex items-center gap-1 text-sm text-muted-foreground">
                <Calendar className="h-3 w-3" />
                Last modified: {new Date(draft.lastModified).toLocaleString()}
              </span>
              <Badge variant="outline">{draft.pipelineType.toUpperCase()}</Badge>

              {/* Automated Run Badge */}
              {status !== 'manual' && (
                <Badge variant="secondary" className="text-xs">
                  Automated
                </Badge>
              )}

              {/* Status Badge */}
              {status === 'queued' && (
                <Badge variant="secondary" className="flex items-center gap-1">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Queued
                </Badge>
              )}
              {status === 'processing' && (
                <Badge className="flex items-center gap-1 bg-blue-500 hover:bg-blue-600">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Processing
                </Badge>
              )}
              {status === 'needs_attention' && (
                <Badge variant="destructive" className="flex items-center gap-1">
                  <XCircle className="h-3 w-3" />
                  Needs Attention
                </Badge>
              )}
              {status === 'completed' && (
                <Badge className="flex items-center gap-1 bg-green-600 hover:bg-green-700">
                  <CheckCircle className="h-3 w-3" />
                  Completed
                </Badge>
              )}
            </div>
          </div>

          <div className="flex gap-2">
            {status === 'needs_attention' ? (
              <Button
                onClick={() => onResume(draft)}
                size="sm"
                variant="destructive"
              >
                <AlertCircle className="h-4 w-4 mr-1" />
                Review & Fix
              </Button>
            ) : (
              <Button
                onClick={() => onResume(draft)}
                size="sm"
                disabled={status === 'processing' || status === 'queued'}
              >
                <ArrowRight className="h-4 w-4 mr-1" />
                {status === 'completed' ? 'View' : 'Resume'}
              </Button>
            )}
            <Button
              onClick={() => onDelete(draft.sessionId, draft.pipelineType)}
              variant="ghost"
              size="sm"
              disabled={status === 'processing' || status === 'queued'}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        <div className="space-y-3">
          {/* Error Alert for needs_attention status */}
          {status === 'needs_attention' && sessionStatus?.error_message && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                <div className="font-medium mb-1">Pipeline failed at: {sessionStatus.current_stage}</div>
                <div className="text-sm">{sessionStatus.error_message}</div>
              </AlertDescription>
            </Alert>
          )}

          {/* Progress indicator */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Current step:</span>
              <span className="font-medium">{currentStepName}</span>
            </div>
            <div className="w-full bg-muted rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all ${
                  status === 'needs_attention'
                    ? 'bg-red-500'
                    : status === 'completed'
                    ? 'bg-green-500'
                    : isJobRunning
                    ? 'bg-blue-500 animate-pulse'
                    : 'bg-primary'
                }`}
                style={{ width: `${displayProgress}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Progress</span>
              <span>{displayProgress}%</span>
            </div>

            {/* Show completed stages for automated runs */}
            {sessionStatus && sessionStatus.completed_stages && sessionStatus.completed_stages.length > 0 && (
              <div className="text-xs text-muted-foreground">
                <span className="font-medium">Completed stages:</span> {sessionStatus.completed_stages.join(' → ')}
              </div>
            )}

            {/* Show job message for manual runs */}
            {isJobRunning && progress?.jobMessage && (
              <div className="text-xs text-muted-foreground italic">
                {progress.jobMessage}
              </div>
            )}

            {/* Show timestamp for automated runs */}
            {sessionStatus && (status === 'processing' || status === 'queued') && sessionStatus.started_at && (
              <div className="text-xs text-muted-foreground">
                Started: {new Date(sessionStatus.started_at).toLocaleTimeString()}
              </div>
            )}
          </div>

          {/* Stored data indicator */}
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Database className="h-3 w-3" />
            <span>{draft.keys.length} configuration(s) saved</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// Static helper functions (used as fallback when progress hook returns null)
function getStepNameStatic(draft: DraftSession): string {
  if (draft.currentStep) {
    return draft.currentStep;
  }

  const keys = draft.keys;
  const hasQcConfig = keys.includes('qc_config');
  const hasMetadata = keys.includes('metadata_table');
  const hasCorrection = keys.includes('correction_rules');
  const hasCalibration = keys.includes('calibration_rules') || keys.includes('calibration_table');
  const hasFinalQc = keys.includes('final_qc_params');
  const hasManualEdits = keys.includes('manual_qc_edits');
  const hasFieldEvents = keys.includes('field_events');

  if (hasFinalQc && (hasManualEdits || hasFieldEvents)) return 'Final QC';
  if (hasFinalQc) return 'Final QC';
  if (hasCalibration) return 'Calibration';
  if (hasCorrection) return 'Correction';
  if (hasQcConfig) return 'Initial QC';
  if (hasMetadata) return 'Metadata';
  return 'Loading & Continuity';
}

function getProgressPercentageStatic(draft: DraftSession): number {
  const totalSteps = 7;

  const stepMap: Record<string, number> = {
    'Loading & Continuity': 1,
    'Metadata': 2,
    'Initial QC': 3,
    'Signal Correction': 4,
    'VWC Calibration': 5,
    'Final QC': 6,
    'Production': 7,
  };

  const currentStepName = draft.currentStep || getStepNameStatic(draft);
  const currentStep = stepMap[currentStepName] || 1;

  return Math.round((currentStep / totalSteps) * 100);
}

export function MyDrafts() {
  const [localDrafts, setLocalDrafts] = useState<DraftSession[]>([]);
  const navigate = useNavigate();
  const { confirm } = useConfirmDialog();

  // Fetch server-side sessions (automated runs)
  const { data: serverSessions } = useListSessions('tms');

  // Delete session mutation
  const deleteSession = useDeleteSession();

  useEffect(() => {
    loadLocalDrafts();
  }, []);

  // Combine local and server sessions
  const drafts = React.useMemo(() => {
    const combined: Record<string, DraftSession> = {};

    // Get set of automated session IDs from server
    const automatedSessionIds = new Set(
      serverSessions?.sessions
        .filter(s => s.is_automated)
        .map(s => s.session_id) ?? []
    );

    // Add local drafts (exclude automated ones to avoid duplicates)
    localDrafts.forEach(draft => {
      // Only add if it's not an automated session
      if (!automatedSessionIds.has(draft.sessionId)) {
        combined[draft.sessionId] = draft;
      }
    });

    // Add ONLY automated server sessions
    if (serverSessions?.sessions) {
      serverSessions.sessions.forEach(session => {
        if (session.is_automated) {
          combined[session.session_id] = {
            sessionId: session.session_id,
            pipelineType: session.pipeline_type,
            lastModified: new Date(session.last_modified * 1000).toISOString(),
            keys: [],
          };
        }
      });
    }

    // Convert to array and sort by last modified
    return Object.values(combined).sort((a, b) =>
      new Date(b.lastModified).getTime() - new Date(a.lastModified).getTime()
    );
  }, [localDrafts, serverSessions]);

  const loadLocalDrafts = () => {
    const sessions: Record<string, DraftSession> = {};

    // Scan localStorage for session-related keys
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key) continue;

      // Match keys like: qc_config_<sessionId>, correction_rules_<sessionId>, etc.
      const match = key.match(/^(qc_config|correction_rules|calibration_rules|field_events|manual_qc_edits|final_qc_params|calibration_table|metadata_table|current_step)_(.+)$/);

      if (match) {
        const [, keyType, sessionId] = match;

        if (!sessions[sessionId]) {
          sessions[sessionId] = {
            sessionId,
            pipelineType: 'tms', // Assume TMS for now
            lastModified: new Date().toISOString(),
            keys: [],
          };
        }

        // Store the current step explicitly if available
        if (keyType === 'current_step') {
          const stepData = localStorage.getItem(key);
          if (stepData) {
            sessions[sessionId].currentStep = stepData;
          }
        } else {
          sessions[sessionId].keys.push(keyType);
        }

        // Try to get last modified from the data
        const data = localStorage.getItem(key);
        if (data) {
          try {
            const parsed = JSON.parse(data);
            if (Array.isArray(parsed) && parsed.length > 0 && parsed[0].timestamp) {
              sessions[sessionId].lastModified = parsed[0].timestamp;
            }
          } catch {
            // Ignore parse errors
          }
        }
      }
    }

    // Convert to array
    const draftsArray = Object.values(sessions);
    setLocalDrafts(draftsArray);
  };

  const handleResume = (draft: DraftSession) => {
    // Store the session ID so the wizard can load it
    sessionStorage.setItem('ameliaSessionId', draft.sessionId);

    // Navigate to the wizard with the session ID
    navigate(`/sessions/${draft.sessionId}/wizard?pipeline=${draft.pipelineType}`);
  };

  const handleDelete = async (sessionId: string, pipelineType: string) => {
    const confirmed = await confirm({
      title: 'Delete Session',
      message: 'Delete this session? All data will be permanently removed.',
      confirmText: 'Delete',
      variant: 'destructive',
    });

    if (!confirmed) {
      return;
    }

    try {
      // 1. Delete from server (works for both manual and automated sessions)
      await deleteSession.mutateAsync({ sessionId, pipelineType });

      // 2. Also clean up localStorage (for manual sessions)
      const keysToRemove: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && key.endsWith(`_${sessionId}`)) {
          keysToRemove.push(key);
        }
      }
      keysToRemove.forEach(key => localStorage.removeItem(key));

      // 3. Reload local drafts to update UI
      loadLocalDrafts();

      toast.success('Session deleted successfully');
    } catch (error) {
      console.error('Failed to delete session:', error);
      toast.error('Failed to delete session', {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  };

  return (
    <div className="container mx-auto px-4 py-8 max-w-6xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">My Drafts</h1>
        <p className="text-muted-foreground">
          Continue editing your pipeline runs before publishing
        </p>
      </div>

      {drafts.length === 0 ? (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            No drafts found. Start a new pipeline run from the "Run Pipeline" page.
          </AlertDescription>
        </Alert>
      ) : (
        <div className="grid gap-4">
          {drafts.map((draft) => (
            <DraftCard
              key={draft.sessionId}
              draft={draft}
              onResume={handleResume}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}
