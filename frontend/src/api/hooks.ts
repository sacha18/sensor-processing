/**
 * TanStack Query hooks for API calls
 */
import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';

// Datasets hooks

export function useDatasets(params?: {
  search?: string;
  pipeline_type?: string;
  tags?: string[];
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: ['datasets', params],
    queryFn: () => apiClient.getDatasets(params),
  });
}

export function useDataset(id: string | null) {
  return useQuery({
    queryKey: ['dataset', id],
    queryFn: () => apiClient.getDataset(id!),
    enabled: !!id,
  });
}

export function useDatasetConfig(id: string | null) {
  return useQuery({
    queryKey: ['dataset-config', id],
    queryFn: () => apiClient.getDatasetConfig(id!),
    enabled: !!id,
  });
}

export function usePublishDataset() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: apiClient.publishDataset.bind(apiClient),
    onSuccess: () => {
      // Invalidate datasets list to refetch
      queryClient.invalidateQueries({ queryKey: ['datasets'] });
    },
  });
}

export function useArchiveDataset() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => apiClient.archiveDataset(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['datasets'] });
    },
  });
}

// Pipelines hooks

export function useRunTMSPipeline() {
  return useMutation({
    mutationFn: ({ files, config, user }: {
      files: File[];
      config: Record<string, any>;
      user: string;
    }) => apiClient.runTMSPipeline(files, config, user),
  });
}

export function useJobStatus(jobId: string | null, enabled = true) {
  return useQuery({
    queryKey: ['job-status', jobId],
    queryFn: () => apiClient.getJobStatus(jobId!),
    enabled: !!jobId && enabled,
    refetchInterval: (query) => {
      // Stop polling if job is finished/failed/canceled
      const data = query.state.data;
      if (!data) return 1000;
      if (['finished', 'failed', 'canceled'].includes(data.status)) {
        return false;
      }
      return 1000; // Poll every second while running
    },
  });
}

export function useCancelJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (jobId: string) => apiClient.cancelJob(jobId),
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: ['job-status', jobId] });
    },
  });
}

// Session & Stage hooks

export function useCreateSession() {
  return useMutation({
    mutationFn: ({ files, pipelineType, user }: {
      files: File[];
      pipelineType: string;
      user: string;
    }) => apiClient.createSession(files, pipelineType, user),
  });
}

export function useRunSessionStage() {
  return useMutation({
    mutationFn: ({ sessionId, stageName, pipelineType }: {
      sessionId: string;
      stageName: string;
      pipelineType: string;
    }) => apiClient.runSessionStage(sessionId, stageName, pipelineType),
  });
}

export function useSessionStages(
  sessionId: string | null,
  pipelineType: string
) {
  return useQuery({
    queryKey: ['session-stages', sessionId, pipelineType],
    queryFn: () => apiClient.getSessionStages(sessionId!, pipelineType),
    enabled: !!sessionId,
  });
}

export function useStageData(
  sessionId: string | null,
  stage: string | null,
  pipelineType: string,
  limit: number = 1000
) {
  return useQuery({
    queryKey: ['stage-data', sessionId, stage, pipelineType, limit],
    queryFn: () => apiClient.getStageData(sessionId!, stage!, pipelineType, limit),
    enabled: !!sessionId && !!stage,
    staleTime: 5 * 60 * 1000, // 5 minutes - stage data doesn't change
  });
}

// QC Configuration hooks

export function useQCConfig(sessionId: string | null, pipelineType: string = 'tms') {
  return useQuery({
    queryKey: ['qc-config', sessionId, pipelineType],
    queryFn: () => apiClient.getQCConfig(sessionId!, pipelineType),
    enabled: !!sessionId,
  });
}

export function useUpdateQCConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ sessionId, config, pipelineType }: {
      sessionId: string;
      config: { qc_cfg: Record<string, any> };
      pipelineType?: string;
    }) => apiClient.updateQCConfig(sessionId, config, pipelineType || 'tms'),
    onSuccess: (_, variables) => {
      // Invalidate QC config cache to refetch
      queryClient.invalidateQueries({
        queryKey: ['qc-config', variables.sessionId, variables.pipelineType || 'tms']
      });
    },
  });
}

// Running Job hook - manages job ID in localStorage and state

export function useRunningJob(sessionId: string | null) {
  const storageKey = sessionId ? `running_job_${sessionId}` : null;

  // Initialize from localStorage
  const [runningJobId, setRunningJobIdState] = useState<string | null>(() => {
    if (!storageKey) return null;
    return localStorage.getItem(storageKey);
  });

  // Sync to localStorage when job ID changes
  const setRunningJobId = (jobId: string | null) => {
    setRunningJobIdState(jobId);
    if (storageKey) {
      if (jobId) {
        localStorage.setItem(storageKey, jobId);
      } else {
        localStorage.removeItem(storageKey);
      }
    }
  };

  // Poll job status
  const { data: jobStatus } = useJobStatus(runningJobId, !!runningJobId);

  // Auto-clear when job finishes
  useEffect(() => {
    if (jobStatus?.status && ['finished', 'failed', 'canceled'].includes(jobStatus.status)) {
      setRunningJobId(null);
    }
  }, [jobStatus?.status]);

  return {
    runningJobId,
    setRunningJobId,
    jobStatus,
    isJobRunning: jobStatus?.status === 'started' || jobStatus?.status === 'queued',
  };
}

// Session progress hook - combines current step with running job progress

export interface SessionProgress {
  currentStep: string;
  currentStepNumber: number;
  totalSteps: number;
  overallProgress: number; // 0-100 percentage
  isJobRunning: boolean;
  jobProgress?: number; // 0-100 if job is running
  jobMessage?: string;
  jobStage?: string;
}

export function useSessionProgress(
  sessionId: string | null,
  pipelineType: string = 'tms'
): SessionProgress | null {
  // Get current step from localStorage
  const currentStepLabel = sessionId
    ? localStorage.getItem(`current_step_${sessionId}`) || 'Loading & Continuity'
    : 'Loading & Continuity';

  // Check for running jobs
  const runningJobId = sessionId
    ? localStorage.getItem(`running_job_${sessionId}`)
    : null;

  // Poll job status if there's a running job
  const { data: jobStatus } = useJobStatus(runningJobId, !!runningJobId);

  if (!sessionId) return null;

  const stepMap: Record<string, number> = {
    'Loading & Continuity': 1,
    'Metadata': 2,
    'Initial QC': 3,
    'Signal Correction': 4,
    'VWC Calibration': 5,
    'Final QC': 6,
    'Production': 7,
  };

  const totalSteps = 7;
  const currentStepNumber = stepMap[currentStepLabel] || 1;

  // Calculate overall progress
  let overallProgress = Math.round((currentStepNumber / totalSteps) * 100);

  // If job is running, show more granular progress
  const isJobRunning = jobStatus?.status === 'started' || jobStatus?.status === 'queued';

  if (isJobRunning && jobStatus?.progress) {
    // Blend step progress with job progress
    // For example: step 3/7 = 42%, if job is 50% done within that step
    // Overall = (2/7)*100 + (1/7)*100*(50/100) = 28.6% + 7.1% = 35.7%
    const previousStepsProgress = ((currentStepNumber - 1) / totalSteps) * 100;
    const currentStepProgress = (1 / totalSteps) * 100 * (jobStatus.progress / 100);
    overallProgress = Math.round(previousStepsProgress + currentStepProgress);
  }

  return {
    currentStep: currentStepLabel,
    currentStepNumber,
    totalSteps,
    overallProgress,
    isJobRunning,
    jobProgress: jobStatus?.progress,
    jobMessage: jobStatus?.message,
    jobStage: jobStatus?.current_stage,
  };
}

// Automated Session hooks

export function useCreateAutomatedSession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      files,
      pipelineType,
      user,
      sourceDatasetId,
      metadataFile,
      qcParamsFile,
      correctionsFile,
      calibrationsFile,
      metadataMapping,
      correctionsMapping,
      calibrationsMapping
    }: {
      files: File[];
      pipelineType: string;
      user: string;
      sourceDatasetId?: string;
      metadataFile?: File;
      qcParamsFile?: File;
      correctionsFile?: File;
      calibrationsFile?: File;
      metadataMapping?: Record<string, string>;
      correctionsMapping?: Record<string, string>;
      calibrationsMapping?: Record<string, string>;
    }) => apiClient.createAutomatedSession({
      files,
      pipelineType,
      user,
      sourceDatasetId,
      metadataFile,
      qcParamsFile,
      correctionsFile,
      calibrationsFile,
      metadataMapping,
      correctionsMapping,
      calibrationsMapping
    }),
    onSuccess: () => {
      // Optionally invalidate queries if needed
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
    },
  });
}

export function useSessionStatus(sessionId: string | null, pipelineType: string = 'tms', enabled = true) {
  return useQuery({
    queryKey: ['session-status', sessionId, pipelineType],
    queryFn: () => apiClient.getSessionStatus(sessionId!, pipelineType),
    enabled: !!sessionId && enabled,
    refetchInterval: (query) => {
      // Poll every 5 seconds if status is "processing" or "queued"
      const data = query.state.data;
      if (!data) return 5000;
      if (['processing', 'queued'].includes(data.status)) {
        return 5000;
      }
      return false; // Stop polling for manual, completed, or needs_attention
    },
  });
}

export function useListSessions(pipelineType: string = 'tms') {
  return useQuery({
    queryKey: ['sessions-list', pipelineType],
    queryFn: () => apiClient.listSessions(pipelineType),
    refetchInterval: 10000, // Refresh every 10 seconds to pick up new sessions
  });
}

// Hook to detect if a session is automated or manual
export function useIsAutomatedSession(sessionId: string | null, pipelineType: string = 'tms') {
  const { data: sessionStatus } = useSessionStatus(sessionId, pipelineType, !!sessionId);

  // If we get a valid status response, it's an automated session
  // Manual sessions don't have status.json files
  return {
    isAutomated: sessionStatus?.status !== undefined && sessionStatus?.status !== 'manual',
    status: sessionStatus?.status,
    isLoading: sessionId ? !sessionStatus : false,
  };
}

// Hook to delete a session
export function useDeleteSession() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ sessionId, pipelineType }: { sessionId: string; pipelineType: string }) =>
      apiClient.deleteSession(sessionId, pipelineType),
    onSuccess: () => {
      // Invalidate sessions list to trigger refresh
      queryClient.invalidateQueries({ queryKey: ['sessions-list'] });
    },
  });
}
