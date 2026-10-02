import { useState, useEffect, useRef } from 'react';
import { useStageData, useSessionStages, useRunSessionStage, useJobStatus } from '../../../api/hooks';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card';
import { Loader2, MapPin, Layers, Ruler, AlertTriangle, CheckCircle, Info } from 'lucide-react';
import { Badge } from '../../../components/ui/badge';
import { MetadataUploader } from '../../../components/metadata/MetadataUploader';
import { MetadataTableEditor } from '../../../components/metadata/MetadataTableEditor';

interface MetadataStepProps {
  sessionId: string;
  pipelineType: string;
}

export function MetadataStep({ sessionId, pipelineType }: MetadataStepProps) {
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [seeding, setSeeding] = useState(false);
  const [runningJobId, setRunningJobId] = useState<string | null>(null);
  const jobTriggeredRef = useRef(false);
  const seedingAttemptedRef = useRef(false);

  // Check which stages exist
  const { data: stagesInfo, refetch: refetchStages } = useSessionStages(sessionId, pipelineType);
  const runStage = useRunSessionStage();

  // Poll job status if running
  const { data: jobStatus } = useJobStatus(runningJobId, !!runningJobId);

  // Check if stages exist
  const mergedStageExists = stagesInfo?.stages.some(s => s.base_name === 'merged');
  const metadataStageExists = stagesInfo?.stages.some(s => s.base_name === 'with_metadata');

  // Load stage data - only when stage exists
  const { data, isLoading, error } = useStageData(
    sessionId,
    metadataStageExists ? 'with_metadata' : null,
    pipelineType,
    100
  );
  const { data: excludedData } = useStageData(
    sessionId,
    metadataStageExists ? 'with_metadata__excluded' : null,
    pipelineType,
    1000
  );

  // Auto-trigger with_metadata job if merged exists but with_metadata doesn't (only once)
  useEffect(() => {
    if (stagesInfo && mergedStageExists && !metadataStageExists && !runningJobId && !jobTriggeredRef.current) {
      console.log('Metadata stage not found, triggering job...');
      jobTriggeredRef.current = true;
      runStage.mutateAsync({
        sessionId,
        stageName: 'with_metadata',
        pipelineType
      }).then(result => {
        console.log('Job started:', result.job_id);
        setRunningJobId(result.job_id);
      }).catch(error => {
        console.error('Failed to start job:', error);
        jobTriggeredRef.current = false;
      });
    }
  }, [stagesInfo, mergedStageExists, metadataStageExists, runningJobId, sessionId, pipelineType, runStage]);

  // When job completes, refetch stages list (data will auto-fetch when stage becomes available)
  useEffect(() => {
    if (jobStatus?.status === 'finished') {
      console.log('Job completed, refetching stages...');
      setRunningJobId(null);
      jobTriggeredRef.current = false;
      // Refetch stages list - this will make metadataStageExists=true, which will auto-fetch the data
      refetchStages();
      setRefreshTrigger(prev => prev + 1);
    }
  }, [jobStatus?.status, refetchStages]);

  // Auto-seed metadata on mount - only when metadata stage exists
  useEffect(() => {
    if (!metadataStageExists || seeding || seedingAttemptedRef.current) return;

    const seedMetadata = async () => {
      setSeeding(true);
      seedingAttemptedRef.current = true;
      try {
        const response = await fetch(
          `http://localhost:8000/api/sessions/${sessionId}/metadata/metadata/seed?pipeline_type=${pipelineType}`,
          { method: 'POST' }
        );

        if (response.ok) {
          const result = await response.json();
          if (result.seeded) {
            console.log('Metadata seeded:', result.message);
            setRefreshTrigger(prev => prev + 1);
          }
        }
      } catch (error) {
        console.error('Failed to seed metadata:', error);
      } finally {
        setSeeding(false);
      }
    };

    seedMetadata();
  }, [sessionId, pipelineType, metadataStageExists, seeding]);

  const handleImportComplete = () => {
    setRefreshTrigger(prev => prev + 1);
  };

  // Show loading/job progress
  if (!stagesInfo || runningJobId || isLoading || seeding) {
    return (
      <div className="flex flex-col items-center justify-center py-12 gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        {jobStatus && (
          <div className="text-center">
            <p className="text-sm font-medium">{jobStatus.message || 'Processing...'}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {jobStatus.current_stage}
            </p>
            {jobStatus.progress > 0 && (
              <div className="mt-3 w-64 bg-muted rounded-full h-2">
                <div
                  className="bg-primary h-2 rounded-full transition-all"
                  style={{ width: `${jobStatus.progress}%` }}
                />
              </div>
            )}
          </div>
        )}
        {!jobStatus && (seeding ? <p className="text-sm text-muted-foreground">Seeding metadata...</p> : <p className="text-sm text-muted-foreground">Loading metadata...</p>)}
      </div>
    );
  }

  // Waiting for merged stage
  if (!mergedStageExists) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Info className="h-12 w-12 mx-auto mb-4" />
        <p>Please complete the Loading step first</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12 text-destructive">
        Error loading metadata: {String(error)}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No metadata available yet
      </div>
    );
  }

  // Extract unique metadata values
  const uniqueSensors = new Set(data.data.map((row: any) => row.sensor_id)).size;
  const uniqueSites = new Set(data.data.map((row: any) => row.site).filter(Boolean)).size;
  const uniquePositions = new Set(data.data.map((row: any) => row.position).filter(Boolean)).size;
  const uniqueDepths = new Set(data.data.map((row: any) => row.depth_cm).filter(Boolean)).size;

  // Sample metadata
  const sampleRow = data.data[0] || {};

  // Excluded rows stats
  const hasExcluded = excludedData && excludedData.total_rows > 0;
  const excludedCount = excludedData?.total_rows || 0;

  // Group excluded by sensor and reason
  const excludedBySensor: Record<string, Record<string, number>> = {};
  if (excludedData && excludedData.data) {
    excludedData.data.forEach((row: any) => {
      const sensor = String(row.sensor_id);
      const reason = row.reason || 'unknown';
      if (!excludedBySensor[sensor]) {
        excludedBySensor[sensor] = {};
      }
      excludedBySensor[sensor][reason] = (excludedBySensor[sensor][reason] || 0) + 1;
    });
  }

  return (
    <div className="space-y-6 pb-24">
      <div>
        <h2 className="text-2xl font-bold mb-2">Deployment Metadata</h2>
        <p className="text-muted-foreground">
          Site, treatment, position, and depth information assigned to each sensor
        </p>
      </div>

      {/* Metadata metrics */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Rows</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{data.total_rows.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              with metadata
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Sensors</CardTitle>
            <Layers className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{uniqueSensors}</div>
            <p className="text-xs text-muted-foreground">
              configured
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Sites</CardTitle>
            <MapPin className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{uniqueSites || '-'}</div>
            <p className="text-xs text-muted-foreground">
              deployment sites
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Positions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{uniquePositions || '-'}</div>
            <p className="text-xs text-muted-foreground">
              unique positions
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Depths</CardTitle>
            <Ruler className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{uniqueDepths || '-'}</div>
            <p className="text-xs text-muted-foreground">
              measurement depths
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Info about seeded metadata */}
      <Card className="border-blue-200 bg-blue-50 dark:bg-blue-950">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Info className="h-5 w-5 text-blue-600" />
            <CardTitle className="text-blue-900 dark:text-blue-100">
              Pre-filled Metadata
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-blue-800 dark:text-blue-200">
            Sensors already loaded are pre-filled below with their first observed timestamp as install start,
            and standard near-surface position/channel labels as a suggestion. Upload a file to add more metadata,
            or edit the table directly to correct any sensor installed differently.
          </p>
        </CardContent>
      </Card>

      {/* Metadata Upload */}
      <MetadataUploader
        sessionId={sessionId}
        tableName="metadata"
        pipelineType={pipelineType}
        onImportComplete={handleImportComplete}
      />

      {/* Metadata Table Editor */}
      <MetadataTableEditor
        sessionId={sessionId}
        tableName="metadata"
        pipelineType={pipelineType}
        refreshTrigger={refreshTrigger}
      />

      {/* Metadata columns */}
      <Card>
        <CardHeader>
          <CardTitle>Metadata Columns</CardTitle>
          <CardDescription>
            Deployment information attached to sensor data
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {['site', 'treatment', 'position', 'depth_cm', 'row', 'transect'].map(col => (
              data.columns.includes(col) && (
                <div key={col} className="flex items-center justify-between py-2 border-b">
                  <span className="font-medium capitalize">{col.replace('_', ' ')}</span>
                  <Badge variant="outline">
                    {sampleRow[col] !== null && sampleRow[col] !== undefined
                      ? String(sampleRow[col])
                      : 'Not set'}
                  </Badge>
                </div>
              )
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Sample data */}
      <Card>
        <CardHeader>
          <CardTitle>Data Preview</CardTitle>
          <CardDescription>
            First 10 rows with metadata ({data.total_rows.toLocaleString()} total)
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  {['sensor_id', 'timestamp', 'site', 'position', 'depth_cm', 'signal_raw'].map(col => (
                    data.columns.includes(col) && (
                      <th key={col} className="text-left p-2 font-medium">
                        {col}
                      </th>
                    )
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.data.slice(0, 10).map((row: any, i: number) => (
                  <tr key={i} className="border-b">
                    {['sensor_id', 'timestamp', 'site', 'position', 'depth_cm', 'signal_raw'].map(col => (
                      data.columns.includes(col) && (
                        <td key={col} className="p-2 font-mono text-xs">
                          {row[col] !== null && row[col] !== undefined
                            ? typeof row[col] === 'number'
                              ? row[col].toFixed(1)
                              : String(row[col])
                            : '-'}
                        </td>
                      )
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Excluded Rows */}
      <Card>
        <CardHeader>
          <CardTitle>Readings Outside Installation Period</CardTitle>
          <CardDescription>
            Observations excluded because they fall outside any configured install period
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!hasExcluded ? (
            <div className="flex items-center gap-2 p-4 bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 rounded-md">
              <CheckCircle className="h-5 w-5 text-green-600" />
              <span className="text-sm text-green-900 dark:text-green-100">
                Every reading falls inside a configured install period
              </span>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-start gap-2 p-4 bg-yellow-50 dark:bg-yellow-950 border border-yellow-200 dark:border-yellow-800 rounded-md">
                <AlertTriangle className="h-5 w-5 text-yellow-600 mt-0.5" />
                <div className="text-sm">
                  <p className="font-medium text-yellow-900 dark:text-yellow-100">
                    {excludedCount.toLocaleString()} reading(s) excluded
                  </p>
                  <p className="text-yellow-800 dark:text-yellow-200">
                    No metadata row covers their timestamp. These readings are not included in the working series.
                  </p>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left p-2 font-medium">Sensor ID</th>
                      <th className="text-left p-2 font-medium">Reason</th>
                      <th className="text-right p-2 font-medium">Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(excludedBySensor).map(([sensor, reasons]) =>
                      Object.entries(reasons).map(([reason, count]) => (
                        <tr key={`${sensor}-${reason}`} className="border-b">
                          <td className="p-2 font-mono text-xs">{sensor}</td>
                          <td className="p-2 text-xs">{reason.replace('_', ' ')}</td>
                          <td className="p-2 text-xs text-right">{count}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

    </div>
  );
}
