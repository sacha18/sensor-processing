/**
 * API client for Sensor Data Processor backend
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface Dataset {
  dataset_id: string;
  title: string;
  description: string | null;
  pipeline_type: string;
  created_by: string;
  created_at: string;
  raw_data_source: string | null;
  raw_data_hash: string | null;
  output_path: string;
  output_checksum: string;
  row_count: number | null;
  sensor_count: number | null;
  date_range_start: string | null;
  date_range_end: string | null;
  tags: string[];
  status: string;
}

export interface DatasetListResponse {
  datasets: Dataset[];
  total: number;
  limit: number;
  offset: number;
}

export interface DatasetConfig {
  dataset_id: string;
  title: string;
  pipeline_type: string;
  config: Record<string, any>;
  manual_edits?: Record<string, any> | null;
  metadata_table?: Record<string, any> | null;
  correction_table?: Record<string, any> | null;
  calibration_table?: Record<string, any> | null;
}

export interface JobStatus {
  job_id: string;
  status: string;
  created_at: string | null;
  started_at: string | null;
  ended_at: string | null;
  progress: number;
  current_stage: string | null;
  message: string | null;
  session_id: string | null;
  result?: any;
  error?: string | null;
}

export interface PipelineRunResponse {
  job_id: string;
  session_id: string;
  status: string;
  queue_position: number;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // Datasets API

  async getDatasets(params?: {
    search?: string;
    pipeline_type?: string;
    tags?: string[];
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<DatasetListResponse> {
    const queryParams = new URLSearchParams();

    if (params?.search) queryParams.append('search', params.search);
    if (params?.pipeline_type) queryParams.append('pipeline_type', params.pipeline_type);
    if (params?.tags) params.tags.forEach(tag => queryParams.append('tags', tag));
    if (params?.status) queryParams.append('status', params.status);
    if (params?.limit) queryParams.append('limit', params.limit.toString());
    if (params?.offset) queryParams.append('offset', params.offset.toString());

    const query = queryParams.toString();
    return this.request<DatasetListResponse>(
      `/api/datasets${query ? `?${query}` : ''}`
    );
  }

  async getDataset(id: string): Promise<Dataset> {
    return this.request<Dataset>(`/api/datasets/${id}`);
  }

  async getDatasetConfig(id: string): Promise<DatasetConfig> {
    return this.request<DatasetConfig>(`/api/datasets/${id}/config`);
  }

  async downloadDataset(id: string, filename?: string): Promise<void> {
    const url = `${this.baseUrl}/api/datasets/${id}/download`;
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`Failed to download dataset: ${response.statusText}`);
    }

    const blob = await response.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = filename || `dataset_${id}.parquet`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(downloadUrl);
    document.body.removeChild(a);
  }

  async publishDataset(data: {
    session_id: string;
    title: string;
    description?: string;
    pipeline_type: string;
    created_by: string;
    tags?: string[];
    raw_data_source?: string;
  }): Promise<Dataset> {
    return this.request<Dataset>('/api/datasets', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async archiveDataset(id: string): Promise<{ message: string }> {
    return this.request(`/api/datasets/${id}`, {
      method: 'DELETE',
    });
  }

  async getDatasetAnalysis(
    id: string,
    analysisType: 'daily' | 'monthly' | 'distribution' | 'summary' = 'daily',
    limit: number = 10000
  ): Promise<{
    per_sensor?: Array<Record<string, any>>;
    group_means?: Array<Record<string, any>>;
    monthly_stats?: Array<Record<string, any>>;
    distribution?: Array<Record<string, any>>;
    summary?: Array<Record<string, any>>;
    metadata: {
      value_column: string;
      has_sensor_id: boolean;
      has_timestamp: boolean;
      group_columns: string[];
      all_value_columns: string[];
    };
  }> {
    return this.request(
      `/api/datasets/${id}/analysis?analysis_type=${analysisType}&limit=${limit}`
    );
  }

  // Pipelines API

  async runTMSPipeline(
    files: File[],
    config: Record<string, any>,
    user: string
  ): Promise<PipelineRunResponse> {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    formData.append('config', JSON.stringify(config));
    formData.append('user', user);

    const url = `${this.baseUrl}/api/pipelines/tms/run`;
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async getJobStatus(jobId: string): Promise<JobStatus> {
    return this.request<JobStatus>(`/api/pipelines/jobs/${jobId}`);
  }

  async cancelJob(jobId: string): Promise<{ message: string }> {
    return this.request(`/api/pipelines/jobs/${jobId}`, {
      method: 'DELETE',
    });
  }

  // Sessions & Pipeline Stages API

  async createSession(
    files: File[],
    pipelineType: string,
    user: string
  ): Promise<{
    session_id: string;
    pipeline_type: string;
    user: string;
    files: Array<{ filename: string; size: number }>;
    total_files: number;
  }> {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    formData.append('pipeline_type', pipelineType);
    formData.append('user', user);

    const url = `${this.baseUrl}/api/sessions/create`;
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async runSessionStage(
    sessionId: string,
    stageName: string,
    pipelineType: string
  ): Promise<{
    job_id: string;
    session_id: string;
    stage_name: string;
    pipeline_type: string;
    status: string;
  }> {
    return this.request(
      `/api/sessions/${sessionId}/run-stage/${stageName}?pipeline_type=${pipelineType}`,
      { method: 'POST' }
    );
  }

  async getSessionStages(
    sessionId: string,
    pipelineType: string
  ): Promise<{
    session_id: string;
    pipeline_type: string;
    stages: Array<{
      stage: string;
      base_name: string;
      label: string;
      order: number;
      available: boolean;
      file_size: number;
    }>;
    total_stages: number;
  }> {
    return this.request(
      `/api/sessions/${sessionId}/stages?pipeline_type=${pipelineType}`
    );
  }

  async getStageData(
    sessionId: string,
    stage: string,
    pipelineType: string,
    limit: number = 1000
  ): Promise<{
    session_id: string;
    stage: string;
    pipeline_type: string;
    total_rows: number;
    sampled_rows: number;
    columns: string[];
    data: Record<string, any>[];
  }> {
    return this.request(
      `/api/sessions/${sessionId}/stages/${stage}?pipeline_type=${pipelineType}&limit=${limit}`
    );
  }

  // QC Configuration

  async getQCConfig(sessionId: string, pipelineType: string = 'tms'): Promise<{
    qc_cfg: Record<string, any>;
  }> {
    return this.request(`/api/sessions/${sessionId}/qc-config/${pipelineType}`);
  }

  async updateQCConfig(
    sessionId: string,
    config: { qc_cfg: Record<string, any> },
    pipelineType: string = 'tms'
  ): Promise<{ success: boolean; message: string }> {
    return this.request(`/api/sessions/${sessionId}/qc-config/${pipelineType}`, {
      method: 'PUT',
      body: JSON.stringify(config),
    });
  }

  // Automated Sessions

  async createAutomatedSession(data: {
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
  }): Promise<{
    session_id: string;
    pipeline_type: string;
    user: string;
    job_id: string;
    status: string;
    files: Array<{ filename: string; size: number }>;
    total_files: number;
    config_source: string;
    config_summary: Record<string, boolean>;
  }> {
    const formData = new FormData();

    // Sensor data files
    data.files.forEach(file => formData.append('files', file));
    formData.append('pipeline_type', data.pipelineType);
    formData.append('user', data.user);

    // Config source
    if (data.sourceDatasetId) {
      formData.append('source_dataset_id', data.sourceDatasetId);
    }

    // Config files
    if (data.metadataFile) {
      formData.append('metadata_file', data.metadataFile);
    }
    if (data.qcParamsFile) {
      formData.append('qc_params_file', data.qcParamsFile);
    }
    if (data.correctionsFile) {
      formData.append('corrections_file', data.correctionsFile);
    }
    if (data.calibrationsFile) {
      formData.append('calibrations_file', data.calibrationsFile);
    }

    // Column mappings
    if (data.metadataMapping) {
      formData.append('metadata_mapping', JSON.stringify(data.metadataMapping));
    }
    if (data.correctionsMapping) {
      formData.append('corrections_mapping', JSON.stringify(data.correctionsMapping));
    }
    if (data.calibrationsMapping) {
      formData.append('calibrations_mapping', JSON.stringify(data.calibrationsMapping));
    }

    const url = `${this.baseUrl}/api/sessions/create-automated`;
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async getSessionStatus(
    sessionId: string,
    pipelineType: string = 'tms'
  ): Promise<{
    session_id: string;
    pipeline_type: string;
    status: string;
    current_stage: string | null;
    completed_stages?: string[];
    progress?: number;
    error_message: string | null;
    started_at?: string;
    last_updated?: string;
  }> {
    return this.request(
      `/api/sessions/${sessionId}/status?pipeline_type=${pipelineType}`
    );
  }

  async listSessions(pipelineType: string = 'tms'): Promise<{
    sessions: Array<{
      session_id: string;
      pipeline_type: string;
      last_modified: number;
      status: string;
      is_automated: boolean;
      stage_count: number;
    }>;
  }> {
    return this.request(`/api/sessions/list?pipeline_type=${pipelineType}`);
  }

  async deleteSession(sessionId: string, pipelineType: string = 'tms'): Promise<{
    success: boolean;
    message: string;
  }> {
    return this.request(`/api/sessions/${sessionId}?pipeline_type=${pipelineType}`, {
      method: 'DELETE',
    });
  }

  // Health check

  async healthCheck(): Promise<{ status: string; redis: string }> {
    return this.request('/health');
  }
}

export const apiClient = new ApiClient();
