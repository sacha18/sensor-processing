import { useStageData, useSessionStages, useRunSessionStage, useJobStatus, useQCConfig, useUpdateQCConfig } from '../../../api/hooks';
import { useAlertDialog } from '../../../hooks/useAlertDialog';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card';
import { Loader2, AlertTriangle, CheckCircle, Shield, Thermometer, Droplets, Info, Settings } from 'lucide-react';
import { FacetGridChart } from '../../../components/charts/FacetGridChart';
import { SensorSelector } from '../../../components/ui/SensorSelector';
import { ManualQCEditor } from '../../../components/tms/ManualQCEditor';
import { ManualQCHistory } from '../../../components/tms/ManualQCHistory';
import { ParametersSidebar } from '../../../components/tms/ParametersSidebar';
import { Label } from '../../../components/ui/label';
import { Input } from '../../../components/ui/input';
import { Switch } from '../../../components/ui/switch';
import { useState, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';

interface FinalQCStepProps {
  sessionId: string;
  pipelineType: string;
  onValidate?: () => void;
  showingComparison: boolean;
  onBackToParams?: () => void;
  isAutomated?: boolean;
  automatedStatus?: string;
}

export function FinalQCStep({ sessionId, pipelineType, onValidate, showingComparison, onBackToParams, isAutomated = false, automatedStatus }: FinalQCStepProps) {
  const queryClient = useQueryClient();
  const { showAlert } = useAlertDialog();
  const [runningJobId, setRunningJobId] = useState<string | null>(null);
  const jobTriggeredRef = useRef(false);
  const [isApplyingChanges, setIsApplyingChanges] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  // Final QC configuration state
  const { data: qcConfigData } = useQCConfig(sessionId, pipelineType);
  const updateQCConfig = useUpdateQCConfig();

  // Local state for final_qc_cfg parameters
  const [finalQcParams, setFinalQcParams] = useState({
    vwc_min: 0,
    vwc_max: 0.6,
    freeze_threshold_c: 1.0,
    use_flatline: true,
    flatline_min_run: 48
  });

  // Initialize final QC params from API when loaded
  useEffect(() => {
    if (qcConfigData?.final_qc_cfg) {
      setFinalQcParams(qcConfigData.final_qc_cfg);
      setHasUnsavedChanges(false);
    }
  }, [qcConfigData]);

  // Check which stages exist
  const { data: stagesInfo, refetch: refetchStages } = useSessionStages(sessionId, pipelineType);
  const runStage = useRunSessionStage();

  // Poll job status if running
  const { data: jobStatus } = useJobStatus(runningJobId, !!runningJobId);

  // Check if stages exist
  const calibratedStageExists = stagesInfo?.stages.some(s => s.base_name === 'calibrated');
  const finalStageExists = stagesInfo?.stages.some(s => s.base_name === 'final');

  // Load BEFORE data (calibrated) for comparison
  const { data: beforeData } = useStageData(
    sessionId,
    calibratedStageExists ? 'calibrated' : null,
    pipelineType,
    1000
  );

  // Load AFTER data (final) - current QC results
  const { data, isLoading, error } = useStageData(
    sessionId,
    finalStageExists ? 'final' : null,
    pipelineType,
    1000
  );

  // Auto-trigger final job if calibrated exists but final doesn't
  // BUT only for manual sessions, not automated ones
  useEffect(() => {
    if (isAutomated) {
      // Skip auto-triggering for automated sessions - they should already have all stages
      return;
    }

    if (stagesInfo && calibratedStageExists && !finalStageExists && !runningJobId && !jobTriggeredRef.current) {
      console.log('Final stage not found, triggering job...');
      jobTriggeredRef.current = true;
      runStage.mutateAsync({
        sessionId,
        stageName: 'final',
        pipelineType
      }).then(result => {
        console.log('Final QC job started:', result.job_id);
        setRunningJobId(result.job_id);
      }).catch(error => {
        console.error('Failed to start final QC job:', error);
        jobTriggeredRef.current = false;
      });
    }
    // Reset trigger flag when stage exists (job completed successfully)
    if (finalStageExists && jobTriggeredRef.current) {
      jobTriggeredRef.current = false;
    }
  }, [isAutomated, stagesInfo, calibratedStageExists, finalStageExists, runningJobId, sessionId, pipelineType, runStage]);

  // When job completes, refetch stages list and invalidate stage data
  useEffect(() => {
    if (jobStatus?.status === 'finished') {
      console.log('Final QC job completed, refetching stages and invalidating data...');
      setRunningJobId(null);
      jobTriggeredRef.current = false;
      refetchStages();
      // Invalidate stage data to force refetch
      queryClient.invalidateQueries({ queryKey: ['stage-data', sessionId, 'final', pipelineType] });
    }
  }, [jobStatus?.status, refetchStages, queryClient, sessionId, pipelineType]);

  // Initialize state before any conditional returns
  const uniqueSensors = data ? [...new Set(data.data.map((row: any) => row.sensor_id))] : [];
  const [selectedSensor, setSelectedSensor] = useState<string>('');

  // Update selected sensor when data loads
  useEffect(() => {
    if (!selectedSensor && uniqueSensors.length > 0) {
      setSelectedSensor(uniqueSensors[0]);
    }
  }, [selectedSensor, uniqueSensors]);

  // Helper to update final QC param
  const updateFinalQcParam = (param: string, value: any) => {
    setFinalQcParams(prev => ({
      ...prev,
      [param]: value
    }));
    setHasUnsavedChanges(true);
  };

  // Get all params from localStorage
  const getLocalStorageParams = () => {
    const fieldEventsKey = `field_events_${sessionId}`;
    const fieldEventsStored = localStorage.getItem(fieldEventsKey);
    const fieldEvents = fieldEventsStored ? JSON.parse(fieldEventsStored) : [];

    const correctionKey = `correction_rules_${sessionId}`;
    const correctionStored = localStorage.getItem(correctionKey);
    const correctionTable = correctionStored ? JSON.parse(correctionStored) : [];

    const calibrationKey = `calibration_rules_${sessionId}`;
    const calibrationStored = localStorage.getItem(calibrationKey);
    const calibrationTable = calibrationStored ? JSON.parse(calibrationStored) : [];

    const qcKey = `qc_cfg_${sessionId}`;
    const qcStored = localStorage.getItem(qcKey);
    const qc_cfg = qcStored ? JSON.parse(qcStored) : {};

    return { fieldEvents, correctionTable, calibrationTable, qc_cfg };
  };

  // Apply Final QC changes - save config and re-run final QC
  const handleApplyChanges = async () => {
    setIsApplyingChanges(true);
    try {
      // Get all params from localStorage and current QC config
      const { fieldEvents, correctionTable, calibrationTable } = getLocalStorageParams();

      // Save config (all params including updated final_qc_cfg)
      await updateQCConfig.mutateAsync({
        sessionId,
        config: {
          qc_cfg: qcConfigData?.qc_cfg || {},
          field_events: fieldEvents,
          correction_table: correctionTable,
          calibration_table: calibrationTable,
          final_qc_cfg: finalQcParams
        },
        pipelineType
      });

      // Re-run final job with new parameters
      const result = await runStage.mutateAsync({
        sessionId,
        stageName: 'final',
        pipelineType
      });

      setRunningJobId(result.job_id);
      setHasUnsavedChanges(false);
    } catch (error) {
      console.error('Failed to apply final QC changes:', error);
      showAlert({
        variant: 'error',
        message: 'Failed to apply changes: ' + String(error),
      });
      setIsApplyingChanges(false);
    }
  };

  // Show loading/job progress
  if (!stagesInfo || runningJobId || isLoading) {
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
        {!jobStatus && <p className="text-sm text-muted-foreground">Loading final QC data...</p>}
      </div>
    );
  }

  // Waiting for calibrated stage
  if (!calibratedStageExists) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Info className="h-12 w-12 mx-auto mb-4" />
        <p>Please complete the VWC Calibration step first</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12 text-destructive">
        Error loading final QC data: {String(error)}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No final QC data available yet
      </div>
    );
  }

  // Final QC works on corrected Signal and VWC only
  // QC methods for final stage
  const qcMethods = ['vwc_range', 'freezing', 'vwc_flatline', 'field_event', 'cross_channel'];

  // Count flags by method
  const flagCountsByMethod: Record<string, number> = {};
  qcMethods.forEach(method => {
    const colName = `is_final_qc_${method}`;
    flagCountsByMethod[method] = data.data.filter((row: any) => row[colName] === true || row[colName] === 1).length;
  });

  const totalFlagged = data.data.filter((row: any) => row.is_final_qc === true || row.is_final_qc === 1).length;
  const passedRows = data.sampled_rows - totalFlagged;

  // Find VWC column
  const vwcColumn = data.columns.find(col => col.toLowerCase().includes('vwc')) || 'vwc';

  // Prepare data for selected sensor
  const sensorData = data.data.filter((row: any) => row.sensor_id === selectedSensor);
  const beforeSensorData = beforeData ? beforeData.data.filter((row: any) => row.sensor_id === selectedSensor) : [];

  // Build flags for final QC
  const buildFinalQCFlags = () => {
    const flags: Record<string, boolean[]> = {};
    qcMethods.forEach(method => {
      const colName = `is_final_qc_${method}`;
      flags[method] = sensorData.map((row: any) => row[colName] === true || row[colName] === 1);
    });
    return flags;
  };

  const finalQCFlags = buildFinalQCFlags();

  // 5 panels: Corrected Signal, VWC, T1, T2, T3
  const panels = [
    { name: 'signal_corrected', label: 'Corrected Signal', col: 'signal_corrected_final', flaggable: true },
    { name: 'vwc', label: 'VWC (m³/m³)', col: 'vwc_final', flaggable: true },
    { name: 't1', label: 'T1 (°C)', col: 't1_raw', flaggable: false },
    { name: 't2', label: 'T2 (°C)', col: 't2_raw', flaggable: false },
    { name: 't3', label: 'T3 (°C)', col: 't3_raw', flaggable: false },
  ];

  const channels = panels.map(panel => ({
    name: panel.name,
    label: panel.label,
    data: {
      timestamp: sensorData.map((row: any) => row.timestamp),
      values: {
        [selectedSensor]: sensorData.map((row: any) => {
          const val = row[panel.col];
          return val !== null && val !== undefined ? Number(val) : 0;
        })
      },
      // Only add flags to the flaggable channels (signal_corrected and vwc)
      flags: panel.flaggable ? finalQCFlags : undefined,
    },
  }));

  return (
    <div className="pb-24">
      <div className="mb-6">
        <h2 className="text-2xl font-bold mb-2">
          {showingComparison ? 'Final Quality Control - Before/After Comparison' : 'Final Quality Control'}
        </h2>
        <p className="text-muted-foreground">
          {showingComparison
            ? 'Review the differences between pre-Final QC (calibrated) and post-Final QC data'
            : 'Cross-channel QC on corrected Signal and VWC, on top of per-channel initial QC'
          }
        </p>
      </div>

      <div className="flex gap-6">
        {/* Sidebar for parameters - hidden in comparison mode or automated sessions (except when needs attention) */}
        {!showingComparison && (!isAutomated || automatedStatus === 'needs_attention') && (
          <ParametersSidebar
            title="Final QC Parameters"
            description="Cross-channel quality control settings"
            icon={<Settings className="h-5 w-5" />}
            hasUnsavedChanges={hasUnsavedChanges}
            isApplying={isApplyingChanges}
            onApply={handleApplyChanges}
          >
        {/* VWC Range */}
        <div className="space-y-2">
          <Label className="text-sm font-semibold">VWC Range (m³/m³)</Label>
          <div className="space-y-2">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Min</Label>
              <Input
                type="number"
                step="0.01"
                value={finalQcParams.vwc_min}
                onChange={(e) => updateFinalQcParam('vwc_min', parseFloat(e.target.value))}
                className="h-8"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Max</Label>
              <Input
                type="number"
                step="0.01"
                value={finalQcParams.vwc_max}
                onChange={(e) => updateFinalQcParam('vwc_max', parseFloat(e.target.value))}
                className="h-8"
              />
            </div>
          </div>
        </div>

        {/* Freeze Threshold */}
        <div className="space-y-1.5">
          <Label className="text-sm">Freeze Threshold (°C)</Label>
          <Input
            type="number"
            step="0.1"
            value={finalQcParams.freeze_threshold_c}
            onChange={(e) => updateFinalQcParam('freeze_threshold_c', parseFloat(e.target.value))}
            className="h-8"
          />
          <p className="text-[10px] text-muted-foreground">
            Flag when T1 (soil) drops below this value
          </p>
        </div>

        {/* VWC Flatline Detection */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-sm">VWC Flatline Detection</Label>
            <Switch
              checked={finalQcParams.use_flatline}
              onCheckedChange={(checked) => updateFinalQcParam('use_flatline', checked)}
            />
          </div>
          {finalQcParams.use_flatline && (
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Min Run (steps)</Label>
              <Input
                type="number"
                value={finalQcParams.flatline_min_run}
                onChange={(e) => updateFinalQcParam('flatline_min_run', parseInt(e.target.value))}
                className="h-8"
              />
              <p className="text-[10px] text-muted-foreground">
                Consecutive identical VWC values (48 = 12h @ 15min)
              </p>
            </div>
          )}
        </div>
      </ParametersSidebar>
        )}

      {/* Main content area - full width in comparison mode or automated sessions (except when needs attention) */}
      <div className={(showingComparison || (isAutomated && automatedStatus !== 'needs_attention')) ? "w-full space-y-6" : "flex-1 space-y-6"}>

      {showingComparison && beforeData ? (
        /* BEFORE/AFTER COMPARISON VIEW */
        <>
          {/* Comparison Header with Sensor Selector */}
          <Card className="bg-blue-50 dark:bg-blue-950 border-blue-200">
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold">Before/After Comparison - Review Final QC Results</div>
                  <div className="text-sm text-muted-foreground">
                    Compare pre-Final QC (calibrated) data vs Final QC-processed data
                  </div>
                </div>
                {uniqueSensors.length > 1 && (
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium">Sensor:</span>
                    <SensorSelector
                      sensors={uniqueSensors}
                      selectedSensor={selectedSensor}
                      onSensorChange={setSelectedSensor}
                    />
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Before/After Grid Comparison */}
          <div className="grid grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Before Final QC (Calibrated)</CardTitle>
                <CardDescription>Calibrated data before Final QC</CardDescription>
              </CardHeader>
              <CardContent>
                <FacetGridChart
                  channels={channels.map(channel => ({
                    ...channel,
                    data: {
                      timestamp: beforeSensorData.map((row: any) => row.timestamp),
                      values: {
                        [selectedSensor]: beforeSensorData.map((row: any) => {
                          const val = row[channel.name === 'signal_corrected' ? 'signal_corrected' : channel.name === 'vwc' ? 'vwc' : channel.name];
                          return val !== null && val !== undefined ? Number(val) : 0;
                        })
                      }
                    }
                  }))}
                  height={1000}
                  showLegend={false}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>After Final QC</CardTitle>
                <CardDescription>Final QC flags marked on changed values</CardDescription>
              </CardHeader>
              <CardContent>
                <FacetGridChart
                  channels={channels}
                  height={1000}
                  showLegend={true}
                />
              </CardContent>
            </Card>
          </div>
        </>
      ) : (
        /* NORMAL VIEW (not comparison) */
        <>

      {/* Final QC Metrics - flag counts by method */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Flagged</CardTitle>
            <AlertTriangle className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalFlagged.toLocaleString()}</div>
          </CardContent>
        </Card>

        {qcMethods.map(method => {
          const methodLabels: Record<string, string> = {
            vwc_range: 'VWC Range',
            freezing: 'Freezing',
            vwc_flatline: 'VWC Flatline',
            field_event: 'Field Event',
            cross_channel: 'Cross-Channel',
          };
          const count = flagCountsByMethod[method] || 0;
          return (
            <Card key={method}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{methodLabels[method]}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{count.toLocaleString()}</div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Detail view - single graph per channel */}
      {uniqueSensors.length > 0 && (
        <div>
          <div className="mb-4">
            <h3 className="text-lg font-semibold mb-2">Detail view - corrected Signal, VWC, T1/T2/T3 together</h3>
            {uniqueSensors.length > 1 && (
              <SensorSelector
                sensors={uniqueSensors}
                selectedSensor={selectedSensor}
                onSensorChange={setSelectedSensor}
              />
            )}
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Final QC Results</CardTitle>
              <CardDescription>Final QC flags shown on Signal and VWC only</CardDescription>
            </CardHeader>
            <CardContent>
              <FacetGridChart
                channels={channels}
                height={1000}
                showLegend={true}
              />
            </CardContent>
          </Card>
        </div>
      )}

      {/* QC Methods Legend */}
      <Card>
        <CardHeader>
          <CardTitle>Final QC Methods</CardTitle>
          <CardDescription>
            Cross-channel quality control checks applied post-calibration
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded-full" style={{ backgroundColor: '#fc8452' }}></div>
              <div>
                <div className="text-sm font-medium">VWC Range</div>
                <div className="text-xs text-muted-foreground">VWC values outside physically plausible bounds (0-1 m³/m³)</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded-full" style={{ backgroundColor: '#5470c6' }}></div>
              <div>
                <div className="text-sm font-medium">Freezing</div>
                <div className="text-xs text-muted-foreground">T1 temperature below freeze threshold</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded-full" style={{ backgroundColor: '#fac858' }}></div>
              <div>
                <div className="text-sm font-medium">VWC Flatline</div>
                <div className="text-xs text-muted-foreground">Consecutive identical VWC values</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded-full" style={{ backgroundColor: '#ee6666' }}></div>
              <div>
                <div className="text-sm font-medium">Field Event</div>
                <div className="text-xs text-muted-foreground">Known disturbance periods (harvest, maintenance, etc.)</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded-full" style={{ backgroundColor: '#9a60b4' }}></div>
              <div>
                <div className="text-sm font-medium">Cross-Channel</div>
                <div className="text-xs text-muted-foreground">Multi-variable plausibility checks</div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Manual QC Editing Section - hidden for automated sessions (except when needs attention) */}
      {(!isAutomated || automatedStatus === 'needs_attention') && (
        <>
          <ManualQCEditor
            sessionId={sessionId}
            pipelineType={pipelineType}
            data={data.data}
            sensorOptions={uniqueSensors as string[]}
            onExclusionAdded={handleApplyChanges}
          />

          {/* Manual QC Edit History */}
          <ManualQCHistory
            sessionId={sessionId}
            onRevert={handleApplyChanges}
          />
        </>
      )}
        </>
      )}
      </div>
    </div>
    </div>
  );
}
