import { useStageData, useSessionStages, useRunSessionStage, useJobStatus } from '../../../api/hooks';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card';
import { Loader2, FileCode, Calendar, Database, AlertTriangle, CheckCircle, TrendingDown } from 'lucide-react';
import { Badge } from '../../../components/ui/badge';
import { Button } from '../../../components/ui/button';
import Plot from 'react-plotly.js';
import { useState, useEffect, useRef } from 'react';

interface LoadingStepProps {
  sessionId: string;
  pipelineType: string;
}

export function LoadingStep({ sessionId, pipelineType }: LoadingStepProps) {
  const [showFullDupReport, setShowFullDupReport] = useState(false);
  const [showFullGapReport, setShowFullGapReport] = useState(false);
  const [runningJobId, setRunningJobId] = useState<string | null>(null);
  const jobTriggeredRef = useRef(false);
  const gapReportJobTriggeredRef = useRef(false);

  // Check which stages exist
  const { data: stagesInfo, refetch: refetchStages} = useSessionStages(sessionId, pipelineType);
  const runStage = useRunSessionStage();

  // Poll job status if running
  const { data: jobStatus } = useJobStatus(runningJobId, !!runningJobId);

  // Check if merged and gap_report stages exist
  const mergedStageExists = stagesInfo?.stages.some(s => s.base_name === 'merged');
  const gapReportStageExists = stagesInfo?.stages.some(s => s.stage === 'gap_report');

  // Load stage data - only when stage exists
  const { data: mergedData, isLoading: mergedLoading, error: mergedError } = useStageData(
    sessionId,
    mergedStageExists ? 'merged' : null,
    pipelineType,
    1000
  );
  const { data: dupData } = useStageData(
    sessionId,
    mergedStageExists ? 'merged__dup_report' : null,
    pipelineType,
    100
  );
  const { data: gapData } = useStageData(
    sessionId,
    gapReportStageExists ? 'gap_report' : null,
    pipelineType,
    1000
  );

  // Auto-trigger merge job if stage doesn't exist (only once)
  useEffect(() => {
    if (stagesInfo && !mergedStageExists && !runningJobId && !jobTriggeredRef.current) {
      console.log('Merged stage not found, triggering job...');
      jobTriggeredRef.current = true;
      runStage.mutateAsync({
        sessionId,
        stageName: 'merged',
        pipelineType
      }).then(result => {
        console.log('Job started:', result.job_id);
        setRunningJobId(result.job_id);
      }).catch(error => {
        console.error('Failed to start job:', error);
        jobTriggeredRef.current = false;
      });
    }
  }, [stagesInfo, mergedStageExists, runningJobId, sessionId, pipelineType, runStage]);

  // When job completes, refetch stages list (data will auto-fetch when stage becomes available)
  useEffect(() => {
    if (jobStatus?.status === 'finished') {
      console.log('Job completed, refetching stages...');
      setRunningJobId(null);
      jobTriggeredRef.current = false;
      gapReportJobTriggeredRef.current = false;
      // Refetch stages list - this will make mergedStageExists/gapReportStageExists=true
      refetchStages();
    }
  }, [jobStatus?.status, refetchStages]);

  // Auto-trigger gap_report job once merged exists but gap_report doesn't
  useEffect(() => {
    if (stagesInfo && mergedStageExists && !gapReportStageExists && !runningJobId && !gapReportJobTriggeredRef.current) {
      console.log('Triggering gap_report job...');
      gapReportJobTriggeredRef.current = true;
      runStage.mutateAsync({
        sessionId,
        stageName: 'gap_report',
        pipelineType
      }).then(result => {
        console.log('Gap report job started:', result.job_id);
        setRunningJobId(result.job_id);
      }).catch(error => {
        console.error('Failed to start gap_report job:', error);
        gapReportJobTriggeredRef.current = false;
      });
    }
  }, [stagesInfo, mergedStageExists, gapReportStageExists, runningJobId, sessionId, pipelineType, runStage]);

  // Show loading/job progress
  if (!stagesInfo || runningJobId || mergedLoading) {
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
        {!jobStatus && <p className="text-sm text-muted-foreground">Loading merged data...</p>}
      </div>
    );
  }

  if (mergedError) {
    return (
      <div className="text-center py-12 text-destructive">
        Error loading merged data: {String(mergedError)}
      </div>
    );
  }

  if (!mergedData) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No merged data available yet
      </div>
    );
  }

  // Calculate stats
  const uniqueSensors = [...new Set(mergedData.data.map((row: any) => row.sensor_id))];
  const timestamps = mergedData.data.map((row: any) => new Date(row.timestamp));
  const minDate = timestamps.length > 0 ? new Date(Math.min(...timestamps.map(d => d.getTime()))) : null;
  const maxDate = timestamps.length > 0 ? new Date(Math.max(...timestamps.map(d => d.getTime()))) : null;

  // File summary by sensor and source_file
  const fileSummary: Record<string, any> = {};
  mergedData.data.forEach((row: any) => {
    const key = `${row.sensor_id}|${row.source_file || 'unknown'}`;
    if (!fileSummary[key]) {
      fileSummary[key] = {
        sensor_id: row.sensor_id,
        source_file: row.source_file || 'unknown',
        count: 0,
        timestamps: [],
      };
    }
    fileSummary[key].count++;
    fileSummary[key].timestamps.push(new Date(row.timestamp));
  });

  const fileSummaryArray = Object.values(fileSummary).map((item: any) => ({
    ...item,
    start: item.timestamps.length > 0 ? new Date(Math.min(...item.timestamps.map((d: Date) => d.getTime()))) : null,
    end: item.timestamps.length > 0 ? new Date(Math.max(...item.timestamps.map((d: Date) => d.getTime()))) : null,
  }));

  // Duplicate report
  const hasDuplicates = dupData && dupData.total_rows > 0;
  const conflictingDups = dupData?.data.filter((row: any) => row.conflicting === true || row.conflicting === 1).length || 0;

  return (
    <div className="space-y-6 pb-24">
      <div>
        <h2 className="text-2xl font-bold mb-2">Loading & Continuity</h2>
        <p className="text-muted-foreground">
          Raw data loaded from TOMST sensor files, merged and deduplicated
        </p>
      </div>

      {/* Main Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Observations</CardTitle>
            <Database className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{mergedData.total_rows.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              after merge & deduplication
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Sensors</CardTitle>
            <FileCode className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{uniqueSensors.length}</div>
            <p className="text-xs text-muted-foreground">
              unique sensor IDs
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Time Span</CardTitle>
            <Calendar className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {minDate && maxDate
                ? Math.ceil((maxDate.getTime() - minDate.getTime()) / (1000 * 60 * 60 * 24))
                : 0}
            </div>
            <p className="text-xs text-muted-foreground">
              days covered
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Files Loaded */}
      <Card>
        <CardHeader>
          <CardTitle>Files Loaded</CardTitle>
          <CardDescription>
            {fileSummaryArray.length} file(s) loaded across {uniqueSensors.length} sensor(s)
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-2 font-medium">Sensor ID</th>
                  <th className="text-left p-2 font-medium">Source File</th>
                  <th className="text-right p-2 font-medium">Rows</th>
                  <th className="text-left p-2 font-medium">Start</th>
                  <th className="text-left p-2 font-medium">End</th>
                </tr>
              </thead>
              <tbody>
                {fileSummaryArray.slice(0, 10).map((file: any, i: number) => (
                  <tr key={i} className="border-b">
                    <td className="p-2 font-mono text-xs">{file.sensor_id}</td>
                    <td className="p-2 text-xs">{file.source_file}</td>
                    <td className="p-2 text-xs text-right">{file.count.toLocaleString()}</td>
                    <td className="p-2 text-xs">{file.start?.toLocaleDateString() || '-'}</td>
                    <td className="p-2 text-xs">{file.end?.toLocaleDateString() || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {fileSummaryArray.length > 10 && (
              <p className="text-xs text-muted-foreground mt-2">
                Showing first 10 of {fileSummaryArray.length} files
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Merge & Deduplication */}
      <Card>
        <CardHeader>
          <CardTitle>Merge & Deduplication</CardTitle>
          <CardDescription>
            Duplicate (sensor, timestamp) pairs across downloads
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!hasDuplicates ? (
            <div className="flex items-center gap-2 p-4 bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 rounded-md">
              <CheckCircle className="h-5 w-5 text-green-600" />
              <span className="text-sm text-green-900 dark:text-green-100">
                No duplicate (sensor, timestamp) pairs across downloads
              </span>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-start gap-2 p-4 bg-yellow-50 dark:bg-yellow-950 border border-yellow-200 dark:border-yellow-800 rounded-md">
                <AlertTriangle className="h-5 w-5 text-yellow-600 mt-0.5" />
                <div className="text-sm">
                  <p className="font-medium text-yellow-900 dark:text-yellow-100">
                    {dupData.total_rows} duplicate pairs found
                  </p>
                  <p className="text-yellow-800 dark:text-yellow-200">
                    Keeping most recently downloaded file's row for each duplicate.
                    {conflictingDups > 0 && (
                      <span className="block mt-1 text-red-600 dark:text-red-400 font-medium">
                        {conflictingDups} of these are conflicting (values disagree)
                      </span>
                    )}
                  </p>
                </div>
              </div>

              {dupData && (
                <>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left p-2 font-medium">Sensor ID</th>
                          <th className="text-left p-2 font-medium">Timestamp</th>
                          <th className="text-left p-2 font-medium">Conflicting</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dupData.data.slice(0, showFullDupReport ? undefined : 5).map((row: any, i: number) => (
                          <tr key={i} className="border-b">
                            <td className="p-2 font-mono text-xs">{row.sensor_id}</td>
                            <td className="p-2 text-xs">{row.timestamp}</td>
                            <td className="p-2">
                              {(row.conflicting === true || row.conflicting === 1) ? (
                                <Badge variant="destructive">Yes</Badge>
                              ) : (
                                <Badge variant="outline">No</Badge>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {dupData.data.length > 5 && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setShowFullDupReport(!showFullDupReport)}
                    >
                      {showFullDupReport ? 'Show Less' : `Show All ${dupData.data.length} Duplicates`}
                    </Button>
                  )}
                </>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Continuity - Gap Report */}
      <Card>
        <CardHeader>
          <CardTitle>Continuity - Gap Report</CardTitle>
          <CardDescription>
            Gaps are reported only - never auto-filled at this stage
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!gapData || gapData.total_rows === 0 ? (
            <div className="flex items-center gap-2 p-4 bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 rounded-md">
              <CheckCircle className="h-5 w-5 text-green-600" />
              <span className="text-sm text-green-900 dark:text-green-100">
                No gaps detected beyond the expected sampling step
              </span>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Gap metrics */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Gaps</CardTitle>
                    <TrendingDown className="h-4 w-4 text-orange-500" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">{gapData.total_rows}</div>
                    <p className="text-xs text-muted-foreground">
                      continuity gaps detected
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Missing Steps (total)</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">
                      {gapData.data.reduce((sum: number, row: any) => sum + (row.n_missing_steps || 0), 0)}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      expected observations missing
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Longest Gap</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">
                      {(() => {
                        const durations = gapData.data.map((row: any) => row.gap_duration).filter(Boolean);
                        if (durations.length === 0) return '-';
                        // gap_duration comes as a string like "1 days 02:30:00" or "05:30:00"
                        const longestDuration = durations.reduce((max: string, d: string) => {
                          // Simple comparison - could be improved with proper parsing
                          return d > max ? d : max;
                        }, durations[0]);
                        return String(longestDuration);
                      })()}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      maximum gap duration
                    </p>
                  </CardContent>
                </Card>
              </div>

              {/* Gap table */}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left p-2 font-medium">Sensor ID</th>
                      <th className="text-left p-2 font-medium">Gap Start</th>
                      <th className="text-left p-2 font-medium">Gap End</th>
                      <th className="text-right p-2 font-medium">Expected Step (min)</th>
                      <th className="text-right p-2 font-medium">Missing Steps</th>
                      <th className="text-left p-2 font-medium">Gap Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gapData.data.slice(0, showFullGapReport ? undefined : 5).map((row: any, i: number) => (
                      <tr key={i} className="border-b">
                        <td className="p-2 font-mono text-xs">{row.sensor_id}</td>
                        <td className="p-2 text-xs">{new Date(row.gap_start).toLocaleString()}</td>
                        <td className="p-2 text-xs">{new Date(row.gap_end).toLocaleString()}</td>
                        <td className="p-2 text-xs text-right">{row.expected_step_min}</td>
                        <td className="p-2 text-xs text-right">{row.n_missing_steps}</td>
                        <td className="p-2 text-xs">{row.gap_duration}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {gapData.data.length > 5 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowFullGapReport(!showFullGapReport)}
                >
                  {showFullGapReport ? 'Show Less' : `Show All ${gapData.data.length} Gaps`}
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Timeline - Per-sensor observed readings */}
      <Card>
        <CardHeader>
          <CardTitle>Per-Sensor Timeline</CardTitle>
          <CardDescription>
            Observed readings distribution over time (sampled: {mergedData.sampled_rows} points)
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Plot
            data={uniqueSensors.map((sensorId, idx) => {
              const sensorData = mergedData.data.filter((row: any) => row.sensor_id === sensorId);
              return {
                x: sensorData.map((row: any) => row.timestamp),
                y: Array(sensorData.length).fill(sensorId),
                type: 'scatter' as const,
                mode: 'markers' as const,
                marker: {
                  symbol: 'line-ns',
                  size: 9,
                  line: { width: 2, color: '#5470c6' }
                },
                name: String(sensorId),
                showlegend: false,
                hovertemplate: '%{x}<extra></extra>',
              };
            })}
            layout={{
              height: 70 + 36 * uniqueSensors.length,
              margin: { t: 30, b: 50, l: 120, r: 20 },
              xaxis: {
                title: 'Time',
              },
              yaxis: {
                title: 'Sensor',
                type: 'category',
              },
              hovermode: 'closest',
            }}
            config={{
              displayModeBar: true,
              displaylogo: false,
              toImageButtonOptions: {
                format: 'png',
                filename: 'sensor_timeline',
              },
            }}
            className="w-full"
            useResizeHandler
          />
        </CardContent>
      </Card>
    </div>
  );
}
